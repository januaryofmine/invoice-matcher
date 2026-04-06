export default async function handler(req, res) {
  const token = process.env.BLOB_READ_WRITE_TOKEN;
  const blobUrl =
    "https://popfjh71cfrgw8g8.private.blob.vercel-storage.com/output.json";

  const response = await fetch(blobUrl, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    res.status(502).json({ error: "Failed to fetch data from blob storage" });
    return;
  }

  const data = await response.json();
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", "s-maxage=60, stale-while-revalidate");
  res.status(200).json(data);
}
