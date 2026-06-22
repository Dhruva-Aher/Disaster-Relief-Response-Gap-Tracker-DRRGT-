export const gapColor = (days) => {
  if (days == null) return "#64748b";
  if (days <= 35) return "#22c55e";
  if (days <= 60) return "#eab308";
  if (days <= 90) return "#f97316";
  return "#ef4444";
};

export const gapLabel = (days) => {
  if (days == null) return "Unknown";
  if (days <= 35) return "Fast";
  if (days <= 60) return "Moderate";
  if (days <= 90) return "Slow";
  return "Critical";
};

export const gapBadge = (days) => {
  if (days == null) return "badge badge-blue";
  if (days <= 35) return "badge badge-green";
  if (days <= 60) return "badge badge-yellow";
  if (days <= 90) return "badge badge-orange";
  return "badge badge-red";
};

export const fmtInc = (value) => {
  if (value == null) return "—";
  return `$${Math.round(value / 1000)}k`;
};

export const niceStateName = (abbr) => {
  const map = {
    MS: "Mississippi", WV: "West Virginia", LA: "Louisiana", AL: "Alabama", KY: "Kentucky",
    AR: "Arkansas", TN: "Tennessee", OK: "Oklahoma", SC: "South Carolina", GA: "Georgia",
    NM: "New Mexico", MT: "Montana", TX: "Texas", WY: "Wyoming", ID: "Idaho", FL: "Florida",
    SD: "South Dakota", NC: "North Carolina", ND: "North Dakota", AK: "Alaska", NE: "Nebraska",
    AZ: "Arizona", MO: "Missouri", IA: "Iowa", NV: "Nevada", KS: "Kansas", UT: "Utah",
    IN: "Indiana", OH: "Ohio", MI: "Michigan", CO: "Colorado", VA: "Virginia", IL: "Illinois",
    PA: "Pennsylvania", WI: "Wisconsin", MN: "Minnesota", OR: "Oregon", HI: "Hawaii",
    WA: "Washington", ME: "Maine", CA: "California", NJ: "New Jersey", MD: "Maryland",
    NY: "New York", DE: "Delaware", NH: "New Hampshire", RI: "Rhode Island", VT: "Vermont",
    MA: "Massachusetts", CT: "Connecticut",
  };
  return map[abbr] || abbr;
};

export function correlation(points) {
  if (!points.length) return null;
  const n = points.length;
  const mx = points.reduce((s, p) => s + p.x, 0) / n;
  const my = points.reduce((s, p) => s + p.y, 0) / n;
  const sxy = points.reduce((s, p) => s + (p.x - mx) * (p.y - my), 0);
  const sxx = points.reduce((s, p) => s + (p.x - mx) ** 2, 0);
  const syy = points.reduce((s, p) => s + (p.y - my) ** 2, 0);
  return sxy / Math.sqrt(sxx * syy || 1);
}
