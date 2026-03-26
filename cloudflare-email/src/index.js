const API_TOKEN = "ax_email_secret_token_2026";

function authCheck(request) {
  const auth = request.headers.get("Authorization") || "";
  if (auth !== `Bearer ${API_TOKEN}`) {
    return new Response(JSON.stringify({ error: "unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }
  return null;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function randomString(len = 10) {
  const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
  let result = "";
  for (let i = 0; i < len; i++) {
    result += chars[Math.floor(Math.random() * chars.length)];
  }
  return result;
}

export default {
  // ─── Email Handler: receives incoming emails ───
  async email(message, env) {
    const to = message.to;
    const from = message.from;
    const subject = message.headers.get("subject") || "(no subject)";

    // Read full body
    const reader = message.raw.getReader();
    const chunks = [];
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
    }
    const rawEmail = new TextDecoder().decode(
      new Uint8Array(chunks.reduce((acc, c) => acc + c.length, 0)).map(
        (_, i) => {
          let offset = 0;
          for (const chunk of chunks) {
            if (i < offset + chunk.length) return chunk[i - offset];
            offset += chunk.length;
          }
          return 0;
        }
      )
    );

    // Extract text body (simple: everything after double newline)
    const bodyStart = rawEmail.indexOf("\r\n\r\n");
    const textBody = bodyStart > -1 ? rawEmail.slice(bodyStart + 4) : rawEmail;

    // Store in D1
    await env.DB.prepare(
      `INSERT INTO messages (mailbox_email, from_addr, subject, body, raw_email, received_at)
       VALUES (?, ?, ?, ?, ?, datetime('now'))`
    )
      .bind(to, from, subject, textBody, rawEmail)
      .run();
  },

  // ─── HTTP API Handler ───
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // Health check — no auth needed
    if (path === "/health") {
      return json({ status: "ok", service: "axiomlauncher-email" });
    }

    // All other routes require auth
    const authErr = authCheck(request);
    if (authErr) return authErr;

    // ─── GET /api/v1/domains ───
    if (method === "GET" && path === "/api/v1/domains") {
      return json({
        success: true,
        domains: ["axiomlauncher.online"],
      });
    }

    // ─── POST /api/v1/mailboxes — create mailbox ───
    if (method === "POST" && path === "/api/v1/mailboxes") {
      const username = `user_${randomString(6)}`;
      const email = `${username}@axiomlauncher.online`;
      const mailboxId = crypto.randomUUID();

      await env.DB.prepare(
        `INSERT INTO mailboxes (id, email, username, created_at)
         VALUES (?, ?, ?, datetime('now'))`
      )
        .bind(mailboxId, email, username)
        .run();

      return json({
        success: true,
        email: { address: email, id: mailboxId },
        mailbox_credentials: { mailbox_id: mailboxId },
      });
    }

    // ─── GET /api/v1/mailboxes — list mailboxes ───
    if (method === "GET" && path === "/api/v1/mailboxes") {
      const rows = await env.DB.prepare(
        `SELECT id, email, username, created_at FROM mailboxes ORDER BY created_at DESC LIMIT 100`
      ).all();

      return json({
        success: true,
        items: rows.results.map((r) => ({
          id: r.id,
          email: r.email,
          username: r.username,
          created_at: r.created_at,
        })),
        total: rows.results.length,
      });
    }

    // ─── DELETE /api/v1/mailboxes — delete mailbox ───
    if (method === "DELETE" && path === "/api/v1/mailboxes") {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ error: "invalid json" }, 400);
      }
      const mailboxId = body.mailbox_id;
      if (!mailboxId) return json({ error: "mailbox_id required" }, 400);

      // Delete messages first, then mailbox
      const mb = await env.DB.prepare(
        `SELECT email FROM mailboxes WHERE id = ?`
      )
        .bind(mailboxId)
        .first();

      if (mb) {
        await env.DB.prepare(`DELETE FROM messages WHERE mailbox_email = ?`)
          .bind(mb.email)
          .run();
      }
      await env.DB.prepare(`DELETE FROM mailboxes WHERE id = ?`)
        .bind(mailboxId)
        .run();

      return json({ success: true });
    }

    // ─── GET /api/v1/messages?mailbox_id=... ───
    if (method === "GET" && path === "/api/v1/messages") {
      const mailboxId = url.searchParams.get("mailbox_id");
      if (!mailboxId) return json({ error: "mailbox_id required" }, 400);

      // Get email address for this mailbox
      const mb = await env.DB.prepare(
        `SELECT email FROM mailboxes WHERE id = ?`
      )
        .bind(mailboxId)
        .first();

      if (!mb) return json({ error: "mailbox not found" }, 404);

      const rows = await env.DB.prepare(
        `SELECT id, from_addr, subject, body, received_at
         FROM messages WHERE mailbox_email = ? ORDER BY received_at DESC LIMIT 50`
      )
        .bind(mb.email)
        .all();

      return json({
        success: true,
        items: rows.results,
        messages: rows.results,
        total: rows.results.length,
      });
    }

    return json({ error: "not found" }, 404);
  },
};
