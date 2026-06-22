export function Card({ title, subtitle, children, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      {title || subtitle ? (
        <div className="panel-head">
          <div>
            {title ? <h2 className="panel-title">{title}</h2> : null}
            {subtitle ? <p className="panel-subtitle">{subtitle}</p> : null}
          </div>
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function CardHeader({ children, className = "" }) {
  return <div className={`panel-head ${className}`}><div>{children}</div></div>;
}

export function CardTitle({ children, className = "" }) {
  return <h2 className={`panel-title ${className}`}>{children}</h2>;
}

export function CardContent({ children, className = "" }) {
  return <div className={`${className}`}>{children}</div>;
}
