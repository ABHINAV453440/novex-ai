require("dotenv").config();

const express = require("express");
const cors = require("cors");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const app = express();

const PORT = process.env.PORT || 3000;

const USERS_FILE = path.join(
  __dirname,
  "users.json"
);


/* =====================================================
   APP SETUP
===================================================== */

app.use(cors());

app.use(
  express.json({
    limit: "20mb"
  })
);

app.use(
  express.static(__dirname)
);


/* =====================================================
   USERS FILE
===================================================== */

function ensureUsersFile() {

  if (!fs.existsSync(USERS_FILE)) {

    fs.writeFileSync(
      USERS_FILE,
      JSON.stringify(
        {
          users: []
        },
        null,
        2
      )
    );

  }

}


function loadUsers() {

  ensureUsersFile();

  try {

    const data =
      JSON.parse(
        fs.readFileSync(
          USERS_FILE,
          "utf8"
        )
      );

    if (
      !data ||
      !Array.isArray(data.users)
    ) {
      return [];
    }

    return data.users;

  }

  catch (error) {

    console.error(
      "USERS FILE ERROR:",
      error
    );

    return [];

  }

}


function saveUsers(users) {

  fs.writeFileSync(
    USERS_FILE,
    JSON.stringify(
      {
        users
      },
      null,
      2
    )
  );

}


ensureUsersFile();


/* =====================================================
   PASSWORD HASHING
===================================================== */

function hashPassword(password) {

  const salt =
    crypto.randomBytes(16);

  const hash =
    crypto.scryptSync(
      password,
      salt,
      64
    );

  return (
    salt.toString("hex") +
    ":" +
    hash.toString("hex")
  );

}


function verifyPassword(
  password,
  storedPassword
) {

  try {

    const parts =
      storedPassword.split(":");

    if (parts.length !== 2) {
      return false;
    }

    const salt =
      Buffer.from(
        parts[0],
        "hex"
      );

    const storedHash =
      Buffer.from(
        parts[1],
        "hex"
      );

    const hash =
      crypto.scryptSync(
        password,
        salt,
        64
      );

    return crypto.timingSafeEqual(
      storedHash,
      hash
    );

  }

  catch {

    return false;

  }

}


/* =====================================================
   SESSIONS
===================================================== */

const sessions =
  new Map();


function createSession(userId) {

  const token =
    crypto.randomBytes(48)
      .toString("hex");

  sessions.set(
    token,
    {
      userId,
      createdAt: Date.now()
    }
  );

  return token;

}


function getUserFromToken(token) {

  if (!token) {
    return null;
  }

  const session =
    sessions.get(token);

  if (!session) {
    return null;
  }

  const users =
    loadUsers();

  return (
    users.find(
      user =>
        user.id === session.userId
    ) || null
  );

}


/* =====================================================
   AUTH MIDDLEWARE
===================================================== */

function requireAuth(
  req,
  res,
  next
) {

  const auth =
    req.headers.authorization || "";

  const token =
    auth.startsWith("Bearer ")
      ? auth.slice(7)
      : "";

  const user =
    getUserFromToken(token);

  if (!user) {

    return res.status(401).json({

      success: false,

      error:
        "Login required"

    });

  }

  req.user = user;
  req.token = token;

  next();

}


/* =====================================================
   SIGN UP
===================================================== */

app.post(
  "/api/signup",
  async (req, res) => {

    try {

      const username =
        String(
          req.body?.username || ""
        ).trim();

      const password =
        String(
          req.body?.password || ""
        );


      if (
        username.length < 3 ||
        username.length > 30
      ) {

        return res.status(400).json({

          success: false,

          error:
            "Username 3-30 characters ka hona chahiye."

        });

      }


      if (!/^[a-zA-Z0-9_]+$/.test(username)) {

        return res.status(400).json({

          success: false,

          error:
            "Username me sirf letters, numbers aur _ use karo."

        });

      }


      if (password.length < 6) {

        return res.status(400).json({

          success: false,

          error:
            "Password kam se kam 6 characters ka hona chahiye."

        });

      }


      const users =
        loadUsers();


      const exists =
        users.some(
          user =>
            user.username.toLowerCase() ===
            username.toLowerCase()
        );


      if (exists) {

        return res.status(409).json({

          success: false,

          error:
            "Ye username already registered hai."

        });

      }


      const user = {

        id:
          crypto.randomUUID(),

        username,

        passwordHash:
          hashPassword(password),

        chats: [],

        createdAt:
          new Date().toISOString()

      };


      users.push(user);

      saveUsers(users);


      const token =
        createSession(
          user.id
        );


      res.json({

        success: true,

        token,

        user: {

          id: user.id,

          username:
            user.username

        }

      });

    }

    catch (error) {

      console.error(
        "SIGNUP ERROR:",
        error
      );

      res.status(500).json({

        success: false,

        error:
          "Signup failed"

      });

    }

  }
);


/* =====================================================
   LOGIN
===================================================== */

app.post(
  "/api/login",
  async (req, res) => {

    try {

      const username =
        String(
          req.body?.username || ""
        ).trim();

      const password =
        String(
          req.body?.password || ""
        );


      if (!username || !password) {

        return res.status(400).json({

          success: false,

          error:
            "Username aur password required hai."

        });

      }


      const users =
        loadUsers();


      const user =
        users.find(
          item =>
            item.username.toLowerCase() ===
            username.toLowerCase()
        );


      if (
        !user ||
        !verifyPassword(
          password,
          user.passwordHash
        )
      ) {

        return res.status(401).json({

          success: false,

          error:
            "Username ya password galat hai."

        });

      }


      const token =
        createSession(
          user.id
        );


      res.json({

        success: true,

        token,

        user: {

          id: user.id,

          username:
            user.username

        }

      });

    }

    catch (error) {

      console.error(
        "LOGIN ERROR:",
        error
      );

      res.status(500).json({

        success: false,

        error:
          "Login failed"

      });

    }

  }
);


/* =====================================================
   LOGOUT
===================================================== */

app.post(
  "/api/logout",
  requireAuth,
  (req, res) => {

    sessions.delete(
      req.token
    );

    res.json({

      success: true

    });

  }
);


/* =====================================================
   ME
===================================================== */

app.get(
  "/api/me",
  requireAuth,
  (req, res) => {

    res.json({

      success: true,

      user: {

        id:
          req.user.id,

        username:
          req.user.username

      }

    });

  }
);


/* =====================================================
   HISTORY GET
===================================================== */

app.get(
  "/api/history",
  requireAuth,
  (req, res) => {

    res.json({

      success: true,

      chats:
        req.user.chats || []

    });

  }
);


/* =====================================================
   HISTORY SAVE
===================================================== */

app.post(
  "/api/history",
  requireAuth,
  (req, res) => {

    try {

      const chats =
        req.body?.chats;


      if (!Array.isArray(chats)) {

        return res.status(400).json({

          success: false,

          error:
            "Invalid chat history"

        });

      }


      const users =
        loadUsers();


      const userIndex =
        users.findIndex(
          user =>
            user.id ===
            req.user.id
        );


      if (userIndex === -1) {

        return res.status(404).json({

          success: false,

          error:
            "User not found"

        });

      }


      /*
        Limit stored history
      */

      users[userIndex].chats =
        chats
          .slice(0, 50)
          .map(chat => ({

            id:
              chat.id,

            title:
              String(
                chat.title ||
                "New Chat"
              ).slice(0, 100),

            messages:
              Array.isArray(
                chat.messages
              )
                ? chat.messages
                    .slice(-100)
                    .map(message => ({

                      role:
                        message.role === "user"
                          ? "user"
                          : "ai",

                      text:
                        String(
                          message.text ||
                          ""
                        ).slice(
                          0,
                          10000
                        )

                    }))
                : []

          }));


      saveUsers(users);


      res.json({

        success:
          true

      });

    }

    catch (error) {

      console.error(
        "HISTORY SAVE ERROR:",
        error
      );

      res.status(500).json({

        success: false,

        error:
          "History save failed"

      });

    }

  }
);


/* =====================================================
   OPENROUTER
===================================================== */

async function askOpenRouter(
  message
) {

  if (
    !process.env.OPENROUTER_API_KEY
  ) {

    throw new Error(
      "OPENROUTER_API_KEY missing in .env"
    );

  }


  const response =
    await fetch(
      "https://openrouter.ai/api/v1/chat/completions",
      {

        method:
          "POST",

        headers: {

          Authorization:
            `Bearer ${process.env.OPENROUTER_API_KEY}`,

          "Content-Type":
            "application/json",

          "HTTP-Referer":
            "http://localhost:3000",

          "X-Title":
            "Novex AI"

        },

        body:
          JSON.stringify({

            model:
              "openrouter/free",

            messages: [

              {

                role:
                  "system",

                content: `
You are Novex AI.

Give useful, accurate and concise answers.

Rules:
- Answer the exact question first.
- Simple question: 1-3 sentences.
- Normal question: 2-6 sentences.
- Do not repeat the question.
- Avoid unnecessary introductions.
- Use Hindi/Hinglish when appropriate.
- For coding, give practical code and short explanation.
- For maths, show necessary steps only.
- For study, make answers exam-friendly.
- Only be detailed when the user asks for detail.
`

              },

              {

                role:
                  "user",

                content:
                  message

              }

            ],

            max_tokens:
              600,

            temperature:
              0.4

          })

      }
    );


  const data =
    await response.json();


  if (!response.ok) {

    throw new Error(

      data?.error?.message ||
      "OpenRouter request failed"

    );

  }


  return (
    data?.choices?.[0]?.message?.content ||
    "AI ने कोई response नहीं दिया।"
  );

}


/* =====================================================
   CHAT API
===================================================== */

app.post(
  "/api/chat",
  requireAuth,
  async (req, res) => {

    try {

      const message =
        String(
          req.body?.message ||
          ""
        ).trim();


      if (!message) {

        return res.status(400).json({

          success: false,

          error:
            "Message required"

        });

      }


      const answer =
        await askOpenRouter(
          message
        );


      res.json({

        success:
          true,

        answer,

        provider:
          "openrouter"

      });

    }

    catch (error) {

      console.error(
        "CHAT ERROR:",
        error
      );

      res.status(500).json({

        success:
          false,

        error:
          error.message ||
          "AI request failed"

      });

    }

  }
);


/* =====================================================
   WEB SEARCH
===================================================== */

async function performWebSearch(
  query
) {

  const url =
    "https://html.duckduckgo.com/html/?q=" +
    encodeURIComponent(query) +
    "&kl=in-en&kp=1";


  const response =
    await fetch(
      url,
      {

        headers: {

          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",

          "Accept-Language":
            "en-IN,en;q=0.9,hi;q=0.8"

        }

      }
    );


  if (!response.ok) {

    throw new Error(
      `Web search failed (${response.status})`
    );

  }


  const html =
    await response.text();


  const results = [];


  const regex =
    /<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/gi;


  let match;


  while (
    (match = regex.exec(html)) &&
    results.length < 8
  ) {

    const title =
      cleanHTMLText(
        match[2]
      );


    let resultUrl =
      match[1];


    try {

      if (
        resultUrl.startsWith("/l/?")
      ) {

        const parsed =
          new URL(
            "https://duckduckgo.com" +
            resultUrl
          );


        const realUrl =
          parsed.searchParams.get(
            "uddg"
          );


        if (realUrl) {

          resultUrl =
            realUrl;

        }

      }

    }

    catch {

      /* Keep original URL */

    }


    if (
      title &&
      resultUrl
    ) {

      results.push({

        title,

        url:
          resultUrl,

        snippet:
          ""

      });

    }

  }


  return {

    query,

    results,

    searchUrl:
      "https://duckduckgo.com/?q=" +
      encodeURIComponent(query)

  };

}


/* =====================================================
   AI SEARCH
===================================================== */

app.get(
  "/api/search-ai",
  requireAuth,
  async (req, res) => {

    try {

      const query =
        String(
          req.query.q ||
          ""
        ).trim();


      if (!query) {

        return res.status(400).json({

          success: false,

          error:
            "Search query required"

        });

      }


      const searchData =
        await performWebSearch(
          query
        );


      const sourceText =
        searchData.results
          .map(
            (item, index) =>
              `${index + 1}. ${item.title}
URL: ${item.url}`
          )
          .join(
            "\n\n"
          );


      const prompt = `

You are Novex AI's CURRENT INFORMATION assistant.

USER QUESTION:
${query}

SEARCH RESULTS:
${sourceText}

Answer using only these search results.

Rules:
- Keep answer short and direct.
- Usually 2-5 sentences.
- Do not invent facts.
- Prefer recent information.
- Mention dates when available.
- If results are insufficient, say so.
- Answer in Hindi/Hinglish when appropriate.
`;


      const summary =
        await askOpenRouter(
          prompt
        );


      res.json({

        success:
          true,

        query,

        summary,

        results:
          searchData.results,

        searchUrl:
          searchData.searchUrl,

        provider:
          "openrouter"

      });

    }

    catch (error) {

      console.error(
        "SEARCH AI ERROR:",
        error
      );


      res.status(500).json({

        success:
          false,

        error:
          error.message ||
          "AI search failed"

      });

    }

  }
);


/* =====================================================
   HEALTH
===================================================== */

app.get(
  "/api/status",
  (req, res) => {

    res.json({

      success:
        true,

      app:
        "Novex AI",

      ai:
        Boolean(
          process.env.OPENROUTER_API_KEY
        )

    });

  }
);


/* =====================================================
   HELPER
===================================================== */

function cleanHTMLText(
  text
) {

  return String(text)

    .replace(
      /<[^>]*>/g,
      ""
    )

    .replace(
      /&amp;/g,
      "&"
    )

    .replace(
      /&quot;/g,
      '"'
    )

    .replace(
      /&#x27;/g,
      "'"
    )

    .replace(
      /&#39;/g,
      "'"
    )

    .replace(
      /&lt;/g,
      "<"
    )

    .replace(
      /&gt;/g,
      ">"
    )

    .trim();

}


/* =====================================================
   SERVER
===================================================== */

app.listen(
  PORT,
  () => {

    console.log(
      `Novex AI running at http://localhost:${PORT}`
    );

  }
);