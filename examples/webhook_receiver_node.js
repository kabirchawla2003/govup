const crypto = require("crypto");
const http = require("http");

const port = parseInt(process.env.PORT || "8011", 10);
const secret = process.env.GOVUPDATE_WEBHOOK_SECRET || "change-me";

function verifySignature(rawBody, signatureHeader) {
  if (!signatureHeader) {
    return false;
  }

  const expected = crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
  const provided = String(signatureHeader).replace(/^sha256=/, "");

  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(provided));
}

const server = http.createServer((req, res) => {
  if (req.method !== "POST" || req.url !== "/govupdate/webhook") {
    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: "not_found" }));
    return;
  }

  const chunks = [];
  req.on("data", (chunk) => chunks.push(chunk));
  req.on("end", () => {
    const rawBody = Buffer.concat(chunks);
    const signature = req.headers["x-govupdate-signature"];

    if (!verifySignature(rawBody, signature)) {
      res.writeHead(401, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: false, error: "invalid_signature" }));
      return;
    }

    const payload = JSON.parse(rawBody.toString("utf8"));
    const event = payload.event || {};

    console.log(
      JSON.stringify({
        received: true,
        delivery_id: req.headers["x-govupdate-delivery-id"],
        event_id: req.headers["x-govupdate-event-id"] || event.event_id,
        source_key: req.headers["x-govupdate-source"] || event.source_key,
        title: event.title,
        published_date: event.published_date,
      })
    );

    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(
      JSON.stringify({
        ok: true,
        delivery_id: req.headers["x-govupdate-delivery-id"],
        event_id: req.headers["x-govupdate-event-id"] || event.event_id,
      })
    );
  });
});

server.listen(port, () => {
  console.log(`GovUpdate sample receiver listening on http://localhost:${port}/govupdate/webhook`);
});
