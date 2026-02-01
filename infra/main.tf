terraform {
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } }
}

provider "aws" { region = var.region }

variable "region" { default = "us-east-1" }
variable "project" { default = "drrgt" }
variable "db_password" { sensitive = true }

# --- Networking (uses default VPC for brevity) ---
data "aws_vpc" "default" { default = true }
data "aws_subnets" "default" {
  filter { name = "vpc-id"  values = [data.aws_vpc.default.id] }
}

# --- S3 bucket for raw ingests ---
resource "aws_s3_bucket" "raw" {
  bucket        = "${var.project}-raw-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}
data "aws_caller_identity" "current" {}

# --- RDS PostgreSQL ---
resource "aws_security_group" "db" {
  name   = "${var.project}-db"
  vpc_id = data.aws_vpc.default.id
  ingress { from_port = 5432 to_port = 5432 protocol = "tcp" cidr_blocks = ["10.0.0.0/8"] }
  egress  { from_port = 0 to_port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] }
}

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
}

# --- ElastiCache Redis ---
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${var.project}-redis"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
}

# --- ECR + ECS Fargate ---
resource "aws_ecr_repository" "api" { name = "${var.project}-api" }
resource "aws_ecs_cluster" "main"  { name = "${var.project}-cluster" }

output "db_endpoint"    { value = aws_db_instance.postgres.endpoint }
output "redis_endpoint" { value = aws_elasticache_cluster.redis.cache_nodes[0].address }
output "ecr_repo"       { value = aws_ecr_repository.api.repository_url }
output "raw_bucket"     { value = aws_s3_bucket.raw.bucket }
