terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" { region = var.region }

# ── Variables ─────────────────────────────────────────────────────────────────

variable "region"  { default = "us-east-1" }
variable "project" { default = "drrgt" }
variable "db_password" { sensitive = true }

# app_image is set by CI/CD to the ECR URI with the deployed commit SHA.
# On first apply (before any deploy), use the placeholder; ECS service
# will be updated by the GitHub Actions deploy step immediately after.
variable "app_image" {
  description = "Full ECR image URI, e.g. 123456.dkr.ecr.us-east-1.amazonaws.com/drrgt-api:abc1234"
  default     = "public.ecr.aws/amazonlinux/amazonlinux:latest"
}

# ── Data sources ──────────────────────────────────────────────────────────────

data "aws_caller_identity" "current" {}
data "aws_vpc" "default" { default = true }
data "aws_subnets" "default" {
  filter { name = "vpc-id" values = [data.aws_vpc.default.id] }
}

# ── Locals ────────────────────────────────────────────────────────────────────
# Build connection strings once and reuse across task definitions.

locals {
  db_url    = "postgresql+psycopg://${aws_db_instance.postgres.username}:${var.db_password}@${aws_db_instance.postgres.address}:5432/${aws_db_instance.postgres.db_name}"
  redis_url = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379/0"
}

# ── S3 raw landing zone ───────────────────────────────────────────────────────
# Archives gzipped FEMA / Census JSON before transformation.
# Lifecycle: transition to STANDARD_IA (60% cheaper) after 30 days;
# expire after 365 days to avoid unbounded storage growth.

resource "aws_s3_bucket" "raw" {
  bucket        = "${var.project}-raw-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    id     = "archive-and-expire"
    status = "Enabled"
    filter { prefix = "" }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    expiration { days = 365 }
  }
}

# ── CloudWatch log groups ─────────────────────────────────────────────────────
# 14-day retention keeps costs low. CloudWatch Insights queries land here.

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project}/api"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.project}/worker"
  retention_in_days = 14
}

# ── IAM ───────────────────────────────────────────────────────────────────────
# Two roles:
# 1. ecs_execution — used by ECS control plane: pull image from ECR,
#    push logs to CloudWatch. Uses AWS managed policy.
# 2. ecs_task — used by the running container: write raw data to S3,
#    put custom CloudWatch metrics. Least-privilege inline policy.

resource "aws_iam_role" "ecs_execution" {
  name = "${var.project}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = "${var.project}-ecs-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "ecs_task_policy" {
  name = "${var.project}-ecs-task"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3RawReadWrite"
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.raw.arn,
          "${aws_s3_bucket.raw.arn}/*",
        ]
      },
      {
        Sid      = "CloudWatchCustomMetrics"
        Effect   = "Allow"
        Action   = ["cloudwatch:PutMetricData"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_policy" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = aws_iam_policy.ecs_task_policy.arn
}

# ── Security groups ───────────────────────────────────────────────────────────
# Principle of least privilege:
# - ALB accepts 80/443 from internet.
# - API task accepts 8000 only from ALB security group (not from internet).
# - Worker task has no inbound — it only makes outbound connections.
# - RDS accepts 5432 only from API and Worker task security groups.

resource "aws_security_group" "alb" {
  name   = "${var.project}-alb"
  vpc_id = data.aws_vpc.default.id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${var.project}-alb" }
}

resource "aws_security_group" "api_task" {
  name   = "${var.project}-api-task"
  vpc_id = data.aws_vpc.default.id
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${var.project}-api-task" }
}

resource "aws_security_group" "worker_task" {
  name   = "${var.project}-worker-task"
  vpc_id = data.aws_vpc.default.id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${var.project}-worker-task" }
}

resource "aws_security_group" "db" {
  name   = "${var.project}-db"
  vpc_id = data.aws_vpc.default.id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [
      aws_security_group.api_task.id,
      aws_security_group.worker_task.id,
    ]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "${var.project}-db" }
}

# ── RDS PostgreSQL ────────────────────────────────────────────────────────────
# db.t4g.micro: burstable ARM instance, cheapest option with 20GB storage.
# backup_retention_period=7: point-in-time recovery window; important for a
# project claiming "production-style" — zero retention is a red flag.
# publicly_accessible=false: database is only reachable from inside the VPC.

resource "aws_db_instance" "postgres" {
  identifier              = "${var.project}-db"
  engine                  = "postgres"
  engine_version          = "16.3"
  instance_class          = "db.t4g.micro"
  allocated_storage       = 20
  db_name                 = "drrgt"
  username                = "drrgt"
  password                = var.db_password
  vpc_security_group_ids  = [aws_security_group.db.id]
  skip_final_snapshot     = true
  publicly_accessible     = false
  backup_retention_period = 7
  tags                    = { Name = "${var.project}-db" }
}

# ── ElastiCache Redis ─────────────────────────────────────────────────────────

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${var.project}-redis"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  tags                 = { Name = "${var.project}-redis" }
}

# ── ECR ───────────────────────────────────────────────────────────────────────
# scan_on_push=true: free ECR vulnerability scanning on every push.
# Lifecycle policy keeps the last 10 images; older ones are expired to
# prevent unbounded registry growth.

resource "aws_ecr_repository" "api" {
  name                 = "${var.project}-api"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire images beyond the last 10"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

# ── ECS cluster ───────────────────────────────────────────────────────────────
# containerInsights=enabled: free ECS-level CPU/memory metrics in CloudWatch.
# Without this you only get task-level metrics, not service-level.

resource "aws_ecs_cluster" "main" {
  name = "${var.project}-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# ── ECS task definition: API ──────────────────────────────────────────────────
# 512 CPU / 1024 MB: enough for FastAPI + SQLAlchemy + scipy analytics.
# Health check hits /health/deep — ALB won't route traffic until the
# container has a live DB connection.

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = var.app_image
    essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = [
      { name = "DATABASE_URL", value = local.db_url },
      { name = "REDIS_URL",    value = local.redis_url },
      { name = "RAW_BUCKET",   value = aws_s3_bucket.raw.bucket },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "api"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "curl -sf http://localhost:8000/health/deep || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])
}

# ── ECS task definition: Worker ───────────────────────────────────────────────
# 1024 CPU / 2048 MB: the Pandas + sklearn pipeline peaks at ~1.5GB loading
# 800k PA records into memory for bulk processing. Worker does not serve
# HTTP so it has no ALB target group or health check port mapping.
# concurrency=2: two Celery worker processes; the daily ETL is a single
# long-running task so we don't need more.

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.project}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "worker"
    image     = var.app_image
    essential = true
    command   = [
      "celery", "-A", "app.worker.celery_app.celery_app",
      "worker", "--beat", "-l", "info", "-c", "2",
    ]
    environment = [
      { name = "DATABASE_URL", value = local.db_url },
      { name = "REDIS_URL",    value = local.redis_url },
      { name = "RAW_BUCKET",   value = aws_s3_bucket.raw.bucket },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.worker.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "worker"
      }
    }
  }])
}

# ── ALB ───────────────────────────────────────────────────────────────────────
# Target type = "ip" is required for Fargate (awsvpc network mode).
# deregistration_delay=30: gives in-flight requests 30s to finish during
# rolling deploys before the old task is killed. Default is 300s (too slow
# for a dev project).

resource "aws_lb" "api" {
  name               = "${var.project}-alb"
  internal           = false
  load_balancer_type = "application"
  subnets            = data.aws_subnets.default.ids
  security_groups    = [aws_security_group.alb.id]
}

resource "aws_lb_target_group" "api" {
  name                 = "${var.project}-api-tg"
  port                 = 8000
  protocol             = "HTTP"
  vpc_id               = data.aws_vpc.default.id
  target_type          = "ip"
  deregistration_delay = 30
  health_check {
    path                = "/health/deep"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
    matcher             = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# ── ECS services ─────────────────────────────────────────────────────────────
# lifecycle.ignore_changes = [task_definition] prevents Terraform from
# rolling back a CI/CD-deployed image revision on the next `terraform apply`.
# CI/CD manages the task definition revision; Terraform manages the service config.

resource "aws_ecs_service" "api" {
  name            = "${var.project}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.api_task.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  # Allow up to 200% capacity during rolling deploy so the new task starts
  # before the old one is killed (zero-downtime rollout).
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_lb_listener.http]
}

resource "aws_ecs_service" "worker" {
  name            = "${var.project}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.worker_task.id]
    assign_public_ip = true
  }

  lifecycle {
    ignore_changes = [task_definition]
  }
}

# ── ECS autoscaling (API only) ────────────────────────────────────────────────
# Target tracking on CPU utilisation: scale out at 70%, cool in over 300s
# (prevents flapping). Max 4 tasks keeps cost bounded for a demo project.
# Worker does not autoscale — a single Celery+Beat task is correct; running
# two Beat schedulers would double-fire the daily ETL job.

resource "aws_appautoscaling_target" "api" {
  max_capacity       = 4
  min_capacity       = 1
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "${var.project}-api-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# ── CloudWatch metric filters ─────────────────────────────────────────────────
# The JSON formatter emits {"level": "ERROR", ...} so a JSON filter on
# $.level = "ERROR" extracts the signal without regex fragility.

resource "aws_cloudwatch_log_metric_filter" "etl_errors" {
  name           = "${var.project}-etl-errors"
  pattern        = "{ $.level = \"ERROR\" }"
  log_group_name = aws_cloudwatch_log_group.worker.name
  metric_transformation {
    name      = "ETLErrors"
    namespace = "DRRGT"
    value     = "1"
  }
}

resource "aws_cloudwatch_log_metric_filter" "api_errors" {
  name           = "${var.project}-api-5xx"
  pattern        = "{ $.status >= 500 }"
  log_group_name = aws_cloudwatch_log_group.api.name
  metric_transformation {
    name      = "API5xxErrors"
    namespace = "DRRGT"
    value     = "1"
  }
}

# ── CloudWatch alarms ─────────────────────────────────────────────────────────
# These alarms are wired to no action by default (alarm_actions = []).
# In a real production system you'd add an SNS topic ARN to alert on-call.
# Having the alarms defined (even without actions) means they appear on the
# CloudWatch console and demonstrate operational awareness in interviews.

resource "aws_cloudwatch_metric_alarm" "etl_error_spike" {
  alarm_name          = "${var.project}-etl-error-spike"
  metric_name         = "ETLErrors"
  namespace           = "DRRGT"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_description   = "ETL worker logged >5 ERROR lines in 5 minutes"
  alarm_actions       = []
}

resource "aws_cloudwatch_metric_alarm" "api_p99_latency" {
  alarm_name          = "${var.project}-api-p99-latency"
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  extended_statistic  = "p99"
  period              = 60
  evaluation_periods  = 3
  threshold           = 2.0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_description   = "API p99 response time >2s for 3 consecutive minutes"
  alarm_actions       = []
  dimensions = {
    LoadBalancer = aws_lb.api.arn_suffix
    TargetGroup  = aws_lb_target_group.api.arn_suffix
  }
}

resource "aws_cloudwatch_metric_alarm" "api_5xx_rate" {
  alarm_name          = "${var.project}-api-5xx-rate"
  metric_name         = "API5xxErrors"
  namespace           = "DRRGT"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_description   = "API returned >10 5xx errors in 1 minute"
  alarm_actions       = []
}

# ── Outputs ───────────────────────────────────────────────────────────────────

output "alb_dns_name" {
  value       = aws_lb.api.dns_name
  description = "ALB DNS — paste into browser to reach the API"
}
output "db_address" {
  value       = aws_db_instance.postgres.address
  description = "RDS endpoint (private, only reachable from inside VPC)"
}
output "redis_address" {
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
  description = "ElastiCache Redis endpoint"
}
output "ecr_repository_url" {
  value       = aws_ecr_repository.api.repository_url
  description = "ECR repository URL — used by CI/CD docker push"
}
output "raw_bucket" {
  value       = aws_s3_bucket.raw.bucket
  description = "S3 bucket name for raw FEMA/Census archives"
}
output "ecs_cluster_name" {
  value       = aws_ecs_cluster.main.name
  description = "ECS cluster name — used by CI/CD deploy step"
}
