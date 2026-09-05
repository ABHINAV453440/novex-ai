require("dotenv").config();

const express = require("express");
const cors = require("cors");
const fs = require("fs");
const path = require("path");

const {
    clerkMiddleware,
    getAuth
} = require("@clerk/express");

const app = express();

const PORT =
    process.env.PORT || 3000;

const DATA_FILE =
    path.join(
        __dirname,
        "clerk-users.json"
    );


/* =====================================================
   CHECK ENV
===================================================== */

console.log(
    "CLERK SECRET:",
    Boolean(process.env.CLERK_SECRET_KEY)
);

console.log(
    "OPENROUTER KEY:",
    Boolean(process.env.OPENROUTER_API_KEY)
);


/* =====================================================
   CLERK FIRST
   IMPORTANT:
   Clerk middleware must come BEFORE
   other middleware.
===================================================== */

app.use(
    clerkMiddleware()
);


/* =====================================================
   OTHER MIDDLEWARE
===================================================== */

app.use(
    cors({
        origin: true,
        credentials: true
    })
);

app.use(
    express.json({
        limit: "20mb"
    })
);

app.use(
    express.static(__dirname)
);


/* =====================================================
   HOME
===================================================== */

app.get("/", (req, res) => {

    res.sendFile(
        path.join(
            __dirname,
            "index.html"
        )
    );
});


/* =====================================================
   DATA FILE
===================================================== */

function ensureDataFile() {

    if (!fs.existsSync(DATA_FILE)) {

        fs.writeFileSync(
            DATA_FILE,
            JSON.stringify(
                {
                    users: {}
                },
                null,
                2
            )
        );
    }
}


function loadData() {

    ensureDataFile();

    try {

        const data =
            JSON.parse(
                fs.readFileSync(
                    DATA_FILE,
                    "utf8"
                )
            );

        if (
            !data ||
            typeof data.users !== "object"
        ) {

            return {
                users: {}
            };
        }

        return data;

    } catch (error) {

        console.error(
            "DATA LOAD ERROR:",
            error
        );

        return {
            users: {}
        };
    }
}


function saveData(data) {

    fs.writeFileSync(
        DATA_FILE,
        JSON.stringify(
            data,
            null,
            2
        )
    );
}


ensureDataFile();


/* =====================================================
   AUTH HELPER
===================================================== */

function requireAuth(
    req,
    res,
    next
) {

    try {

        const auth =
            getAuth(req);

        console.log(
            "AUTH CHECK:",
            {
                isAuthenticated:
                    auth.isAuthenticated,

                userId:
                    auth.userId || null,

                sessionId:
                    auth.sessionId || null
            }
        );

        if (!auth.isAuthenticated) {

            return res.status(401).json({
                success: false,
                error: "Login required"
            });
        }

        req.userId =
            auth.userId;

        req.sessionId =
            auth.sessionId;

        next();

    } catch (error) {

        console.error(
            "AUTH ERROR:",
            error
        );

        return res.status(401).json({
            success: false,
            error:
                "Authentication failed"
        });
    }
}


/* =====================================================
   ME
===================================================== */

app.get(
    "/api/me",
    requireAuth,
    (req, res) => {

        const data =
            loadData();

        if (
            !data.users[req.userId]
        ) {

            data.users[req.userId] = {
                chats: []
            };

            saveData(data);
        }

        res.json({
            success: true,
            userId:
                req.userId
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

        const data =
            loadData();

        const user =
            data.users[req.userId];

        const chats =
            user?.chats || [];

        res.json({
            success: true,

            history:
                chats,

            chats:
                chats
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

            if (
                !Array.isArray(chats)
            ) {

                return res.status(400).json({
                    success: false,
                    error:
                        "Invalid chat history"
                });
            }

            const data =
                loadData();

            if (
                !data.users[req.userId]
            ) {

                data.users[req.userId] = {
                    chats: []
                };
            }

            data.users[req.userId].chats =
                chats
                    .slice(0, 50)
                    .map(chat => ({

                        id:
                            String(
                                chat.id ||
                                Date.now()
                            ),

                        title:
                            String(
                                chat.title ||
                                "New Chat"
                            ).slice(0, 100),

                        message:
                            String(
                                chat.message ||
                                chat.title ||
                                "New Chat"
                            ).slice(0, 200),

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
                                : [],

                        createdAt:
                            chat.createdAt ||
                            Date.now()
                    }));

            saveData(data);

            res.json({
                success: true
            });

        } catch (error) {

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
   DELETE ONE CHAT
===================================================== */

app.delete(
    "/api/history/:index",
    requireAuth,
    (req, res) => {

        try {

            const index =
                Number(
                    req.params.index
                );

            const data =
                loadData();

            if (
                !data.users[req.userId]
            ) {

                return res.json({
                    success: true
                });
            }

            const chats =
                data.users[req.userId]
                    .chats || [];

            if (
                Number.isInteger(index) &&
                index >= 0 &&
                index < chats.length
            ) {

                chats.splice(
                    index,
                    1
                );
            }

            saveData(data);

            res.json({
                success: true
            });

        } catch (error) {

            console.error(
                "DELETE CHAT ERROR:",
                error
            );

            res.status(500).json({
                success: false,
                error:
                    "Chat delete failed"
            });
        }
    }
);


/* =====================================================
   CLEAR HISTORY
===================================================== */

app.delete(
    "/api/history",
    requireAuth,
    (req, res) => {

        try {

            const data =
                loadData();

            if (
                !data.users[req.userId]
            ) {

                data.users[req.userId] = {
                    chats: []
                };

            } else {

                data.users[req.userId]
                    .chats = [];
            }

            saveData(data);

            res.json({
                success: true
            });

        } catch (error) {

            console.error(
                "CLEAR HISTORY ERROR:",
                error
            );

            res.status(500).json({
                success: false,
                error:
                    "History clear failed"
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

    const apiKey =
        process.env.OPENROUTER_API_KEY;

    if (!apiKey) {

        throw new Error(
            "OPENROUTER_API_KEY missing in .env"
        );
    }

    const response =
        await fetch(
            "https://openrouter.ai/api/v1/chat/completions",
            {
                method: "POST",

                headers: {

                    "Authorization":
                        "Bearer " + apiKey,

                    "Content-Type":
                        "application/json",

                    "HTTP-Referer":
                        `http://localhost:${PORT}`,

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

                                content:
`You are Novex AI.

Answer the exact question first.

Use Hindi/Hinglish when appropriate.

Simple questions:
1-3 sentences.

Normal questions:
2-6 sentences.

Coding:
Give practical working code.

Math:
Show only necessary steps.

Study:
Make answers exam-friendly.

Do not unnecessarily repeat the question.`
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

    let data = {};

    try {

        data =
            await response.json();

    } catch (error) {

        throw new Error(
            "OpenRouter returned invalid JSON."
        );
    }

    if (!response.ok) {

        console.error(
            "OPENROUTER ERROR:",
            data
        );

        throw new Error(
            data?.error?.message ||
            `OpenRouter HTTP ${response.status}`
        );
    }

    const answer =
        data?.choices?.[0]
            ?.message?.content;

    if (!answer) {

        throw new Error(
            "OpenRouter ne answer nahi diya."
        );
    }

    return answer;
}


/* =====================================================
   CHAT
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

            console.log(
                "CHAT:",
                req.userId,
                message
            );

            const answer =
                await askOpenRouter(
                    message
                );

            /* Save chat */

            const data =
                loadData();

            if (
                !data.users[req.userId]
            ) {

                data.users[req.userId] = {
                    chats: []
                };
            }

            const chats =
                data.users[req.userId]
                    .chats || [];

            chats.unshift({

                id:
                    Date.now().toString(),

                title:
                    message.slice(0, 100),

                message:
                    message.slice(0, 200),

                messages: [

                    {
                        role:
                            "user",

                        text:
                            message
                    },

                    {
                        role:
                            "ai",

                        text:
                            answer
                    }
                ],

                createdAt:
                    Date.now()
            });

            data.users[req.userId]
                .chats =
                chats.slice(0, 50);

            saveData(data);

            res.json({
                success: true,

                answer:

                    answer,

                provider:
                    "openrouter"
            });

        } catch (error) {

            console.error(
                "CHAT ERROR:",
                error
            );

            res.status(500).json({
                success: false,

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
                        "Mozilla/5.0",

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
        /<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/gi;

    let match;

    while (
        (match =
            regex.exec(html)) &&
        results.length < 8
    ) {

        const title =
            cleanHTMLText(
                match[2]
            );

        let resultUrl =
            match[1];

        try {

            const parsed =
                new URL(
                    resultUrl,
                    "https://duckduckgo.com"
                );

            const realUrl =
                parsed.searchParams.get(
                    "uddg"
                );

            if (realUrl) {
                resultUrl =
                    realUrl;
            }

        } catch (_) {}

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

app.post(
    "/api/search-ai",
    requireAuth,
    async (req, res) => {

        try {

            const query =
                String(
                    req.body?.message ||
                    req.body?.q ||
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
                            `${index + 1}. ${item.title}\nURL: ${item.url}`
                    )
                    .join("\n\n");

            const prompt =
`You are Novex AI's current-information assistant.

User question:
${query}

Search results:
${sourceText}

Use only these results.

Rules:
- Do not invent facts.
- Keep the answer direct.
- Mention dates when available.
- Answer in Hindi/Hinglish when appropriate.`;

            const answer =
                await askOpenRouter(
                    prompt
                );

            res.json({

                success:
                    true,

                query,

                answer,

                reply:
                    answer,

                summary:
                    answer,

                results:
                    searchData.results,

                searchUrl:
                    searchData.searchUrl
            });

        } catch (error) {

            console.error(
                "SEARCH ERROR:",
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
   STATUS
===================================================== */

app.get(
    "/api/status",
    (req, res) => {

        res.json({

            success:
                true,

            app:
                "Novex AI",

            clerk:
                Boolean(
                    process.env.CLERK_SECRET_KEY
                ),

            openrouter:
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
   START SERVER
===================================================== */

app.listen(
    PORT,
    () => {

        console.log("");
        console.log(
            "===================================="
        );
        console.log(
            "🚀 NOVEX AI SERVER RUNNING"
        );
        console.log(
            `🌐 http://localhost:${PORT}`
        );
        console.log(
            "🔐 CLERK AUTH ENABLED"
        );
        console.log(
            "🤖 OPENROUTER ENABLED"
        );
        console.log(
            "===================================="
        );
        console.log("");
    }
);