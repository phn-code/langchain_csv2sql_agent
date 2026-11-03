import type { Analysis, Report, Schema } from "../contract";

type Col = Schema["tables"][number]["columns"][number];

const col = (name: string, type: string, comment: string | null, extra: Partial<Col> = {}): Col => ({
  name,
  type,
  comment,
  primary_key: false,
  references: null,
  ...extra,
});
const pk = { primary_key: true };
const fk = (ref: string) => ({ references: ref });

export const fixtureSchema: Schema = {
  tables: [
    {
      name: "sales_transactions",
      comment: "Loaded from sales_transactions.csv: 3,333 rows. Withheld for privacy: card_number (payment card).",
      columns: [
        col("transaction_id", "BIGINT", "From CSV column transactionID.", pk),
        col("customer_id", "BIGINT", "From CSV column customerID.", fk("sales_customers(customer_id)")),
        col("franchise_id", "BIGINT", "From CSV column franchiseID.", fk("sales_franchises(franchise_id)")),
        col("date_time", "TIMESTAMP", "From CSV column dateTime. Range 2024-05-01 to 2024-05-17."),
        col("product", "TEXT", "From CSV column product. 6 distinct values, e.g. 'Golden Gate Ginger', 'Tokyo Tidbits'."),
        col("quantity", "BIGINT", "From CSV column quantity."),
        col("unit_price", "BIGINT", "From CSV column unitPrice."),
        col("total_price", "BIGINT", "From CSV column totalPrice."),
        col("payment_method", "TEXT", "From CSV column paymentMethod. One of: 'amex', 'mastercard', 'visa'."),
      ],
    },
    {
      name: "sales_customers",
      comment:
        "Loaded from sales_customers.csv: 300 rows. Withheld for privacy: first_name (person name), last_name (person name), email_address (email), phone_number (phone number), address (street address).",
      columns: [
        col("customer_id", "BIGINT", "From CSV column customerID.", pk),
        col("city", "TEXT", "From CSV column city."),
        col("state", "TEXT", "From CSV column state."),
        col("country", "TEXT", "From CSV column country. 9 distinct values."),
        col("continent", "TEXT", "From CSV column continent."),
        col("postal_zip_code", "BIGINT", "From CSV column postal_zip_code."),
        col("gender", "TEXT", "From CSV column gender. One of: 'female', 'male', 'other'."),
      ],
    },
    {
      name: "sales_franchises",
      comment: "Loaded from sales_franchises.csv: 48 rows.",
      columns: [
        col("franchise_id", "BIGINT", "From CSV column franchiseID.", pk),
        col("name", "TEXT", "From CSV column name."),
        col("city", "TEXT", "From CSV column city."),
        col("district", "TEXT", "From CSV column district."),
        col("country", "TEXT", "From CSV column country."),
        col("size", "TEXT", "From CSV column size. One of: 'L', 'M', 'S', 'XS'."),
        col("supplier_id", "BIGINT", "From CSV column supplierID.", fk("sales_suppliers(supplier_id)")),
      ],
    },
    {
      name: "sales_suppliers",
      comment: "Loaded from sales_suppliers.csv: 27 rows.",
      columns: [
        col("supplier_id", "BIGINT", "From CSV column supplierID.", pk),
        col("name", "TEXT", "From CSV column name."),
        col("ingredient", "TEXT", "From CSV column ingredient."),
        col("continent", "TEXT", "From CSV column continent."),
        col("city", "TEXT", "From CSV column city."),
        col("approved", "BOOLEAN", "From CSV column approved. One of: 'Y', 'N'."),
      ],
    },
    {
      name: "media_customer_reviews",
      comment: "Loaded from media_customer_reviews.csv: 204 rows.",
      columns: [
        col("new_id", "BIGINT", "From CSV column new_id.", pk),
        col("review", "TEXT", "From CSV column review. Free text."),
        col("franchise_id", "BIGINT", "From CSV column franchiseID.", fk("sales_franchises(franchise_id)")),
        col("review_date", "TIMESTAMP", "From CSV column review_date."),
      ],
    },
    {
      name: "media_gold_reviews_chunked",
      comment: "Loaded from media_gold_reviews_chunked.csv: 336 rows.",
      columns: [
        col("chunk_id", "TEXT", "From CSV column chunk_id.", pk),
        col("franchise_id", "BIGINT", "From CSV column franchiseID.", fk("sales_franchises(franchise_id)")),
        col("review_date", "TIMESTAMP", "From CSV column review_date."),
        col("chunked_text", "TEXT", "From CSV column chunked_text. Free text."),
        col("review_uri", "TEXT", "From CSV column review_uri."),
      ],
    },
  ],
};

export const fixtureReport: Report = {
  tables: [
    {
      name: "sales_transactions",
      source: "sales_transactions.csv",
      rows: 3333,
      primary_key: "transaction_id",
      rejected_rows: [],
      rejected_row_count: 0,
      withheld: [{ column: "card_number", pii: "payment card" }],
    },
    {
      name: "sales_customers",
      source: "sales_customers.csv",
      rows: 300,
      primary_key: "customer_id",
      rejected_rows: [],
      rejected_row_count: 0,
      withheld: [
        { column: "first_name", pii: "person name" },
        { column: "last_name", pii: "person name" },
        { column: "email_address", pii: "email" },
        { column: "phone_number", pii: "phone number" },
        { column: "address", pii: "street address" },
      ],
    },
    {
      name: "sales_franchises",
      source: "sales_franchises.csv",
      rows: 48,
      primary_key: "franchise_id",
      rejected_rows: [],
      rejected_row_count: 0,
      withheld: [],
    },
    {
      name: "sales_suppliers",
      source: "sales_suppliers.csv",
      rows: 27,
      primary_key: "supplier_id",
      rejected_rows: [],
      rejected_row_count: 0,
      withheld: [],
    },
    {
      name: "media_customer_reviews",
      source: "media_customer_reviews.csv",
      rows: 204,
      primary_key: "new_id",
      rejected_rows: [
        { line: 58, reason: "Unterminated quoted field" },
        { line: 141, reason: "Expected 4 fields, found 6" },
        { line: 177, reason: "review_date: 'yesterday' is not a date" },
      ],
      rejected_row_count: 3,
      withheld: [],
    },
    {
      name: "media_gold_reviews_chunked",
      source: "media_gold_reviews_chunked.csv",
      rows: 336,
      primary_key: "chunk_id",
      rejected_rows: [],
      rejected_row_count: 0,
      withheld: [],
    },
  ],
  relationships: [
    { table: "sales_transactions", column: "customer_id", parent_table: "sales_customers", parent_column: "customer_id", offset: 0, origin: "name" },
    { table: "sales_transactions", column: "franchise_id", parent_table: "sales_franchises", parent_column: "franchise_id", offset: 0, origin: "name" },
    { table: "sales_franchises", column: "supplier_id", parent_table: "sales_suppliers", parent_column: "supplier_id", offset: 0, origin: "name" },
    { table: "media_customer_reviews", column: "franchise_id", parent_table: "sales_franchises", parent_column: "franchise_id", offset: 3000000, origin: "ai" },
    { table: "media_gold_reviews_chunked", column: "franchise_id", parent_table: "sales_franchises", parent_column: "franchise_id", offset: 3000000, origin: "ai" },
  ],
  rejected_relationships: [
    {
      table: "sales_customers",
      column: "postal_zip_code",
      parent_table: "sales_franchises",
      reason: "Only 4% of values match sales_franchises.zipcode; too few to be a key.",
    },
  ],
};

function rng(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296;
    return s / 4294967296;
  };
}

const rand = rng(7);

const days = Array.from({ length: 17 }, (_, i) => `2024-05-${String(i + 1).padStart(2, "0")}`);
const dailyRows = days.map((d, i) => [d, Math.round(1900 + 380 * Math.sin(i / 2.2) + rand() * 520 + (i % 7 === 5 ? 650 : 0))]);

export const chartAnalysis: Analysis = {
  question: "Plot daily revenue over time",
  sql: `SELECT CAST(date_time AS DATE) AS day,
       SUM(total_price) AS revenue
FROM sales_transactions
GROUP BY day
ORDER BY day;`,
  result: {
    columns: [
      { name: "day", kind: "temporal" },
      { name: "revenue", kind: "number" },
    ],
    rows: dailyRows,
    truncated: false,
    elapsed_ms: 14,
  },
  chart: {
    $schema: "https://vega.github.io/schema/vega-lite/v6.json",
    data: { values: dailyRows.map(([day, revenue]) => ({ day, revenue })) },
    mark: { type: "line", point: true, interpolate: "monotone" },
    encoding: {
      x: { field: "day", type: "temporal", title: "Day", axis: { format: "%b %d" } },
      y: { field: "revenue", type: "quantitative", title: "Revenue (USD)" },
      tooltip: [
        { field: "day", type: "temporal", title: "Day" },
        { field: "revenue", type: "quantitative", title: "Revenue", format: ",.0f" },
      ],
    },
  },
  failures: [],
};

const products = ["Golden Gate Ginger", "Tokyo Tidbits", "Outback Oatmeal", "Austin Almond Biscotti", "Orchard Oasis", "Pearly Pies"];
const tableRows = Array.from({ length: 100 }, (_, i) => {
  const qty = 1 + Math.floor(rand() * 40);
  const day = 1 + Math.floor((i / 100) * 17);
  const hour = 8 + Math.floor(rand() * 11);
  return [
    1000000 + i * 7 + Math.floor(rand() * 5),
    `2024-05-${String(day).padStart(2, "0")} ${String(hour).padStart(2, "0")}:${String(Math.floor(rand() * 60)).padStart(2, "0")}:00`,
    products[Math.floor(rand() * products.length)] ?? "Pearly Pies",
    qty,
    qty * 3,
    i % 17 === 4 ? null : 2000000 + Math.floor(rand() * 300),
  ];
});

export const tableAnalysis: Analysis = {
  question: "Show every transaction paid with amex",
  sql: `SELECT transaction_id, date_time, product, quantity, total_price, customer_id
FROM sales_transactions
WHERE payment_method = 'amex'
ORDER BY date_time;`,
  result: {
    columns: [
      { name: "transaction_id", kind: "number" },
      { name: "date_time", kind: "temporal" },
      { name: "product", kind: "text" },
      { name: "quantity", kind: "number" },
      { name: "total_price", kind: "number" },
      { name: "customer_id", kind: "number" },
    ],
    rows: tableRows,
    truncated: true,
    elapsed_ms: 9,
  },
  chart: null,
  failures: [],
};

export const correctedAnalysis: Analysis = {
  question: "Which franchises have the most reviews, and who supplies them?",
  sql: `SELECT f.name AS franchise,
       s.name AS supplier,
       s.ingredient,
       COUNT(r.new_id) AS reviews
FROM media_customer_reviews AS r
JOIN sales_franchises AS f ON f.franchise_id = r.franchise_id
JOIN sales_suppliers AS s ON s.supplier_id = f.supplier_id
GROUP BY f.name, s.name, s.ingredient
ORDER BY reviews DESC
LIMIT 5;`,
  result: {
    columns: [
      { name: "franchise", kind: "text" },
      { name: "supplier", kind: "text" },
      { name: "ingredient", kind: "text" },
      { name: "reviews", kind: "number" },
    ],
    rows: [
      ["Sweet Sydney Spoonfuls", "Southern Sweets Co.", "Sugar", 31],
      ["Tokyo Treat Tower", "Sakura Spice Merchants", "Cinnamon", 27],
      ["Rue de Croissant", "Moulin de Provence", "Flour", 24],
      ["Golden Gate Bakes", "Pacific Grain Mill", "Flour", 19],
      ["Maple Leaf Morsels", "Northern Dairy Collective", "Butter", 17],
    ],
    truncated: false,
    elapsed_ms: 22,
  },
  chart: null,
  failures: [
    {
      sql: `SELECT f.name, s.name, COUNT(*) AS reviews
FROM media_customer_reviews r
JOIN sales_franchises f ON f.franchiseID = r.franchiseID
JOIN sales_suppliers s ON s.supplier_id = f.supplier_id
GROUP BY f.name, s.name
ORDER BY reviews DESC;`,
      error: 'Binder Error: Table "f" does not have a column named "franchiseID". Candidate: "franchise_id"',
    },
    {
      sql: `SELECT name, s.name AS supplier, COUNT(r.new_id) AS reviews
FROM media_customer_reviews r
JOIN sales_franchises f ON f.franchise_id = r.franchise_id
JOIN sales_suppliers s ON s.supplier_id = f.supplier_id
GROUP BY name, supplier
ORDER BY reviews DESC
LIMIT 5;`,
      error: 'Binder Error: Ambiguous reference to column name "name" (use: "f.name" or "s.name")',
    },
  ],
};

export const countryRows = [
  ["USA", 9472],
  ["Japan", 6104],
  ["Australia", 5310],
  ["France", 4588],
  ["Canada", 3927],
  ["Germany", 2860],
  ["Netherlands", 1932],
  ["Sweden", 1405],
] as const;

export const countryAnalysis: Analysis = {
  question: "Revenue by country as a bar chart",
  sql: `SELECT c.country, SUM(t.total_price) AS revenue
FROM sales_transactions AS t
JOIN sales_customers AS c ON c.customer_id = t.customer_id
GROUP BY c.country
ORDER BY revenue DESC;`,
  result: {
    columns: [
      { name: "country", kind: "text" },
      { name: "revenue", kind: "number" },
    ],
    rows: countryRows.map((r) => [...r]),
    truncated: false,
    elapsed_ms: 11,
  },
  chart: {
    $schema: "https://vega.github.io/schema/vega-lite/v6.json",
    data: { values: countryRows.map(([country, revenue]) => ({ country, revenue })) },
    mark: { type: "bar" },
    encoding: {
      y: { field: "country", type: "nominal", sort: "-x", title: null },
      x: { field: "revenue", type: "quantitative", title: "Revenue (USD)" },
      tooltip: [
        { field: "country", type: "nominal" },
        { field: "revenue", type: "quantitative", format: ",.0f" },
      ],
    },
  },
  failures: [],
};
