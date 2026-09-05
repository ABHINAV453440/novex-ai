```js
"use strict";

/* =========================================================
   NOVEX AI
   Clerk Login + Authenticated API + Chat + History
   FIXED CLERK INITIALIZATION
========================================================= */

let clerkReady = false;
let appStarted = false;
let loginMounted = false;
let loginWatcher = null;


/* =========================================================
   START
========================================================= */

document.addEventListener("DOMContentLoaded", () => {
    initializeNovex();
    loadTheme();
});


/* =========================================================
   CLERK INITIALIZE
========================================================= */

async function initializeNovex() {

    try {

        updateStatus("Loading login...");

        /*
         * Clerk script load hone ka wait.
         */
        let attempts = 0;

        while (
            typeof window.Clerk === "undefined" &&
            attempts < 150
        ) {
            await sleep(100);
            attempts++;
        }

        if (typeof window.Clerk === "undefined") {

            console.error(
                "Clerk object not found after waiting."
            );

            showLoginError(
                "Clerk login load nahi ho paya. Page ko Ctrl + F5 se refresh karo."
            );

            return;
        }


        /*
         * Clerk.load()
         */
        if (
            typeof window.Clerk.load === "function" &&
            !clerkReady
        ) {

            await window.Clerk.load({
                signInForceRedirectUrl:
                    window.location.href,
                signUpForceRedirectUrl:
                    window.location.href
            });

            clerkReady = true;
        }


        /*
         * Login state check.
         */
        if (window.Clerk.isSignedIn) {

            await openNovexApp();

        } else {

            showLogin();

        }

    } catch (error) {

        console.error(
            "CLERK INITIALIZATION ERROR:",
            error
        );

        showLoginError(
            "Login system start nahi ho paya: " +
            (error.message || "Unknown error")
        );
    }
}


/* =========================================================
   SLEEP
========================================================= */

function sleep(ms) {

    return new Promise(
        resolve => setTimeout(resolve, ms)
    );
}


/* =========================================================
   LOGIN SCREEN
========================================================= */

function showLogin() {

    const authScreen =
        document.getElementById("authScreen");

    const app =
        document.getElementById("app");

    const signIn =
        document.getElementById("clerkSignIn");


    if (!authScreen || !signIn) {

        console.error(
            "authScreen or clerkSignIn not found."
        );

        return;
    }


    authScreen.classList.remove("hidden");


    if (app) {
        app.classList.add("hidden");
    }


    /*
     * Existing Clerk UI remove.
     */
    if (!loginMounted) {

        try {

            signIn.innerHTML = "";

            /*
             * Modern Clerk mount.
             */
            if (
                typeof window.Clerk.mountSignIn ===
                "function"
            ) {

                window.Clerk.mountSignIn(
                    signIn,
                    {
                        signInForceRedirectUrl:
                            window.location.href
                    }
                );

                loginMounted = true;

            } else {

                throw new Error(
                    "Clerk mountSignIn unavailable."
                );
            }

        } catch (error) {

            console.error(
                "CLERK SIGN-IN MOUNT ERROR:",
                error
            );

            loginMounted = false;

            showLoginError(
                "Clerk login UI load nahi ho paya: " +
                (error.message || "Unknown error")
            );

            return;
        }
    }


    /*
     * Login state watcher.
     */
    watchLogin();
}


/* =========================================================
   LOGIN WATCHER
========================================================= */

function watchLogin() {

    if (loginWatcher) {
        return;
    }


    /*
     * Clerk event listener.
     * Agar available hai to use karo.
     */
    try {

        if (
            window.Clerk &&
            typeof window.Clerk.addListener ===
            "function"
        ) {

            window.Clerk.addListener(
                ({ session }) => {

                    if (
                        session &&
                        window.Clerk.isSignedIn
                    ) {

                        openNovexApp();
                    }
                }
            );
        }

    } catch (error) {

        console.warn(
            "Clerk listener unavailable:",
            error
        );
    }


    /*
     * Backup polling.
     */
    loginWatcher =
        setInterval(
            async () => {

                try {

                    if (
                        window.Clerk &&
                        window.Clerk.isSignedIn
                    ) {

                        clearInterval(
                            loginWatcher
                        );

                        loginWatcher = null;

                        await openNovexApp();
                    }

                } catch (error) {

                    console.error(
                        "LOGIN WATCH ERROR:",
                        error
                    );
                }

            },
            700
        );
}


/* =========================================================
   OPEN NOVEX APP
========================================================= */

async function openNovexApp() {

    if (appStarted) {
        return;
    }


    /*
     * Login confirm.
     */
    if (
        !window.Clerk ||
        !window.Clerk.isSignedIn
    ) {

        showLogin();

        return;
    }


    appStarted = true;


    if (loginWatcher) {

        clearInterval(
            loginWatcher
        );

        loginWatcher = null;
    }


    const authScreen =
        document.getElementById("authScreen");

    const app =
        document.getElementById("app");


    if (authScreen) {
        authScreen.classList.add("hidden");
    }


    if (app) {
        app.classList.remove("hidden");
    }


    setupUser();


    updateStatus("Loading...");


    /*
     * User backend record.
     */
    try {

        await authFetch(
            "/api/me",
            {
                method: "GET"
            }
        );

    } catch (error) {

        console.warn(
            "ME API:",
            error
        );
    }


    /*
     * Chat history.
     */
    try {

        await loadHistory();

    } catch (error) {

        console.warn(
            "History loading:",
            error
        );
    }


    updateStatus(
        "Ready to help"
    );
}


/* =========================================================
   USER
========================================================= */

function setupUser() {

    try {

        const user =
            window.Clerk?.user;


        if (!user) {
            return;
        }


        const username =
            user.firstName ||
            user.username ||
            user.primaryEmailAddress?.emailAddress ||
            "User";


        const nameElement =
            document.getElementById(
                "loggedUsername"
            );


        if (nameElement) {

            nameElement.textContent =
                username;
        }


        const avatar =
            document.getElementById(
                "userAvatar"
            );


        if (
            avatar &&
            user.imageUrl
        ) {

            avatar.innerHTML = "";

            const img =
                document.createElement("img");

            img.src =
                user.imageUrl;

            img.alt =
                "User";

            img.style.width =
                "100%";

            img.style.height =
                "100%";

            img.style.objectFit =
                "cover";

            img.style.borderRadius =
                "50%";

            avatar.appendChild(img);
        }

    } catch (error) {

        console.error(
            "USER SETUP ERROR:",
            error
        );
    }
}


/* =========================================================
   STATUS
========================================================= */

function updateStatus(text) {

    const status =
        document.getElementById(
            "statusText"
        );


    if (status) {

        status.textContent =
            text || "Ready to help";
    }
}


/* =========================================================
   GET CLERK TOKEN
========================================================= */

async function getAuthToken() {

    if (
        !window.Clerk ||
        !window.Clerk.isSignedIn
    ) {

        throw new Error(
            "Login required"
        );
    }


    /*
     * Current Clerk session.
     */
    let session =
        window.Clerk.session;


    /*
     * Session ready hone ka short wait.
     */
    if (!session) {

        for (
            let i = 0;
            i < 30;
            i++
        ) {

            await sleep(100);

            session =
                window.Clerk.session;

            if (session) {
                break;
            }
        }
    }


    if (
        !session ||
        typeof session.getToken !==
        "function"
    ) {

        throw new Error(
            "Clerk session token available nahi hai."
        );
    }


    const token =
        await session.getToken();


    if (!token) {

        throw new Error(
            "Clerk session token nahi mila."
        );
    }


    return token;
}


/* =========================================================
   AUTHENTICATED FETCH
========================================================= */

async function authFetch(
    url,
    options = {}
) {

    const token =
        await getAuthToken();


    const headers = {
        ...(options.headers || {}),
        "Authorization":
            `Bearer ${token}`,
        "Content-Type":
            "application/json"
    };


    return fetch(
        url,
        {
            ...options,
            headers
        }
    );
}


/* =========================================================
   MAIN SEND
========================================================= */

async function sendMessage() {

    const input =
        document.getElementById(
            "userInput"
        );


    if (!input) {
        return;
    }


    const message =
        input.value.trim();


    if (!message) {
        return;
    }


    addMessage(
        message,
        "user"
    );


    input.value = "";

    autoResize(input);


    const welcome =
        document.getElementById(
            "welcome"
        );


    if (welcome) {

        welcome.classList.add(
            "hidden"
        );
    }


    hideSpecialAreas();


    updateStatus(
        "Thinking..."
    );


    try {

        const lower =
            message.toLowerCase();


        /* =================================================
           IMAGE
        ================================================= */

        if (
            lower.includes("generate image") ||
            lower.includes("image banao") ||
            lower.includes("image bana") ||
            lower.includes("photo banao") ||
            lower.includes("picture banao") ||
            lower.includes("draw") ||
            lower.includes("ai image")
        ) {

            await generateImage(
                message
            );
        }


        /* =================================================
           WEBSITE
        ================================================= */

        else if (
            lower.includes("website banao") ||
            lower.includes("website bana") ||
            lower.includes("website create") ||
            lower.includes("html website") ||
            lower.includes("website")
        ) {

            await generateWebsite(
                message
            );
        }


        /* =================================================
           WEB SEARCH
        ================================================= */

        else if (
            lower.includes("latest") ||
            lower.includes("today") ||
            lower.includes("news") ||
            lower.includes("search web") ||
            lower.includes("internet par") ||
            lower.includes("google par")
        ) {

            await searchWeb(
                message
            );
        }


        /* =================================================
           NORMAL AI
        ================================================= */

        else {

            await askAI(
                message
            );
        }

    } catch (error) {

        console.error(
            "SEND MESSAGE ERROR:",
            error
        );


        addMessage(
            "❌ " +
            (
                error.message ||
                "Unknown error"
            ),
            "ai"
        );


        updateStatus(
            "Error"
        );
    }


    /*
     * History failure se main chat crash nahi hogi.
     */
    try {

        await loadHistory();

    } catch (_) {}
}


/* =========================================================
   AI CHAT
========================================================= */

async function askAI(message) {

    const response =
        await authFetch(
            "/api/chat",
            {
                method: "POST",

                body:
                    JSON.stringify({
                        message:
                            message
                    })
            }
        );


    let data = {};


    try {

        data =
            await response.json();

    } catch (error) {

        throw new Error(
            "Server ne valid response nahi diya. HTTP " +
            response.status
        );
    }


    console.log(
        "NOVEX API RESPONSE:",
        data
    );


    if (!response.ok) {

        throw new Error(
            data.error ||
            data.message ||
            "AI request failed. HTTP " +
            response.status
        );
    }


    const answer =
        data.answer ||
        data.reply ||
        data.content ||
        "AI ne koi answer nahi diya.";


    addMessage(
        answer,
        "ai"
    );


    updateStatus(
        "Ready to help"
    );
}


/* =========================================================
   HISTORY
========================================================= */

async function loadHistory() {

    try {

        const response =
            await authFetch(
                "/api/history",
                {
                    method: "GET"
                }
            );


        let data = {};


        try {

            data =
                await response.json();

        } catch (_) {

            return;
        }


        if (!response.ok) {

            console.error(
                "HISTORY ERROR:",
                data
            );

            return;
        }


        const list =
            document.getElementById(
                "historyList"
            );


        if (!list) {
            return;
        }


        list.innerHTML = "";


        const history =
            Array.isArray(
                data.history
            )
                ? data.history
                : (
                    Array.isArray(
                        data.chats
                    )
                        ? data.chats
                        : []
                );


        history.forEach(
            (item, index) => {

                const row =
                    document.createElement(
                        "div"
                    );


                row.className =
                    "history-item";


                const title =
                    document.createElement(
                        "span"
                    );


                title.textContent =
                    item.message ||
                    item.title ||
                    "New Chat";


                const button =
                    document.createElement(
                        "button"
                    );


                button.textContent =
                    "🗑️";


                button.title =
                    "Delete";


                button.type =
                    "button";


                button.onclick =
                    () => deleteChat(
                        index
                    );


                row.appendChild(
                    title
                );


                row.appendChild(
                    button
                );


                list.appendChild(
                    row
                );
            }
        );

    } catch (error) {

        console.error(
            "HISTORY ERROR:",
            error
        );
    }
}


/* =========================================================
   DELETE ONE CHAT
========================================================= */

async function deleteChat(index) {

    try {

        const response =
            await authFetch(
                `/api/history/${index}`,
                {
                    method:
                        "DELETE"
                }
            );


        if (response.ok) {

            await loadHistory();
        }

    } catch (error) {

        console.error(
            "DELETE ERROR:",
            error
        );
    }
}


/* =========================================================
   CLEAR HISTORY
========================================================= */

async function clearHistory() {

    try {

        const response =
            await authFetch(
                "/api/history",
                {
                    method:
                        "DELETE"
                }
            );


        if (response.ok) {

            await loadHistory();
        }

    } catch (error) {

        console.error(
            "CLEAR HISTORY ERROR:",
            error
        );
    }
}


/* =========================================================
   IMAGE — PUTER
========================================================= */

async function generateImage(prompt) {

    const area =
        document.getElementById(
            "imageArea"
        );


    const loading =
        document.getElementById(
            "imageLoading"
        );


    const result =
        document.getElementById(
            "imageResult"
        );


    const promptText =
        document.getElementById(
            "imagePromptText"
        );


    if (area) {

        area.classList.remove(
            "hidden"
        );
    }


    if (loading) {

        loading.classList.remove(
            "hidden"
        );
    }


    if (promptText) {

        promptText.textContent =
            prompt;
    }


    if (result) {

        result.innerHTML = "";
    }


    try {

        if (
            typeof puter === "undefined" ||
            !puter.ai
        ) {

            throw new Error(
                "Puter service load nahi hua."
            );
        }


        const image =
            await puter.ai.txt2img(
                prompt
            );


        if (result) {

            result.appendChild(
                image
            );
        }


        addMessage(
            "✅ Image generate ho gayi.",
            "ai"
        );


        updateStatus(
            "Ready to help"
        );

    } catch (error) {

        console.error(
            "IMAGE ERROR:",
            error
        );


        addMessage(
            "❌ Image generate nahi ho payi: " +
            error.message,
            "ai"
        );


        updateStatus(
            "Image Error"
        );

    } finally {

        if (loading) {

            loading.classList.add(
                "hidden"
            );
        }
    }
}


/* =========================================================
   WEBSITE
========================================================= */

async function generateWebsite(prompt) {

    const area =
        document.getElementById(
            "websiteArea"
        );


    const loading =
        document.getElementById(
            "websiteLoading"
        );


    const result =
        document.getElementById(
            "websiteResult"
        );


    if (area) {

        area.classList.remove(
            "hidden"
        );
    }


    if (loading) {

        loading.classList.remove(
            "hidden"
        );
    }


    if (result) {

        result.innerHTML = "";
    }


    try {

        const response =
            await authFetch(
                "/api/chat",
                {
                    method: "POST",

                    body:
                        JSON.stringify({
                            message:
`Create a complete modern website.

User request:
${prompt}

Return complete working HTML code with CSS and JavaScript.`
                        })
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.error ||
                "Website generation failed."
            );
        }


        const answer =
            data.answer ||
            data.reply ||
            "";


        if (result) {

            const pre =
                document.createElement(
                    "pre"
                );


            pre.textContent =
                answer;


            result.appendChild(
                pre
            );
        }


        addMessage(
            "✅ Website code ready hai.",
            "ai"
        );

    } catch (error) {

        console.error(
            "WEBSITE ERROR:",
            error
        );


        addMessage(
            "❌ Website error: " +
            error.message,
            "ai"
        );

    } finally {

        if (loading) {

            loading.classList.add(
                "hidden"
            );
        }
    }


    updateStatus(
        "Ready to help"
    );
}


/* =========================================================
   WEB SEARCH
========================================================= */

async function searchWeb(message) {

    const area =
        document.getElementById(
            "searchArea"
        );


    const loading =
        document.getElementById(
            "searchLoading"
        );


    const result =
        document.getElementById(
            "searchResult"
        );


    if (area) {

        area.classList.remove(
            "hidden"
        );
    }


    if (loading) {

        loading.classList.remove(
            "hidden"
        );
    }


    try {

        const response =
            await authFetch(
                "/api/search-ai",
                {
                    method: "POST",

                    body:
                        JSON.stringify({
                            message:
                                message
                        })
                }
            );


        const data =
            await response.json();


        if (!response.ok) {

            throw new Error(
                data.error ||
                "Search failed."
            );
        }


        const answer =
            data.answer ||
            data.reply ||
            data.summary ||
            "";


        if (result) {

            result.innerHTML = "";


            const div =
                document.createElement(
                    "div"
                );


            div.textContent =
                answer;


            result.appendChild(
                div
            );
        }


        addMessage(
            answer,
            "ai"
        );

    } catch (error) {

        console.error(
            "SEARCH ERROR:",
            error
        );


        addMessage(
            "❌ Search error: " +
            error.message,
            "ai"
        );

    } finally {

        if (loading) {

            loading.classList.add(
                "hidden"
            );
        }
    }


    updateStatus(
        "Ready to help"
    );
}


/* =========================================================
   MESSAGE
========================================================= */

function addMessage(
    text,
    type
) {

    const messages =
        document.getElementById(
            "messages"
        );


    if (!messages) {
        return;
    }


    const div =
        document.createElement(
            "div"
        );


    div.className =
        `message ${type}`;


    const content =
        document.createElement(
            "div"
        );


    content.className =
        "message-content";


    content.textContent =
        String(
            text ?? ""
        );


    div.appendChild(
        content
    );


    messages.appendChild(
        div
    );


    messages.scrollTop =
        messages.scrollHeight;
}


/* =========================================================
   INPUT RESIZE
========================================================= */

function autoResize(
    textarea
) {

    if (!textarea) {
        return;
    }


    textarea.style.height =
        "auto";


    textarea.style.height =
        textarea.scrollHeight +
        "px";
}


/* =========================================================
   ENTER KEY
========================================================= */

function handleKeyPress(
    event
) {

    if (
        event.key === "Enter" &&
        !event.shiftKey
    ) {

        event.preventDefault();

        sendMessage();
    }
}


/* =========================================================
   VOICE
========================================================= */

function startVoiceInput() {

    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;


    if (!SpeechRecognition) {

        alert(
            "Is browser me Voice Input supported nahi hai."
        );

        return;
    }


    const recognition =
        new SpeechRecognition();


    recognition.lang =
        "hi-IN";


    recognition.interimResults =
        false;


    recognition.continuous =
        false;


    recognition.onresult =
        function(event) {

            const text =
                event.results[0][0]
                    .transcript;


            const input =
                document.getElementById(
                    "userInput"
                );


            if (input) {

                input.value =
                    text;


                autoResize(
                    input
                );
            }
        };


    recognition.onerror =
        function(event) {

            console.error(
                "VOICE ERROR:",
                event.error
            );
        };


    try {

        recognition.start();

    } catch (error) {

        console.error(
            "VOICE START ERROR:",
            error
        );
    }
}


/* =========================================================
   THEME MENU
========================================================= */

function toggleThemeMenu() {

    const menu =
        document.getElementById(
            "themeMenu"
        );


    if (menu) {

        menu.classList.toggle(
            "show"
        );
    }
}


/* =========================================================
   SET THEME
========================================================= */

function setTheme(
    theme
) {

    document.body.classList.remove(
        "theme-black",
        "theme-white"
    );


    document.body.classList.add(
        `theme-${theme}`
    );


    localStorage.setItem(
        "novex-theme",
        theme
    );


    const menu =
        document.getElementById(
            "themeMenu"
        );


    if (menu) {

        menu.classList.remove(
            "show"
        );
    }
}


/* =========================================================
   LOAD THEME
========================================================= */

function loadTheme() {

    const theme =
        localStorage.getItem(
            "novex-theme"
        );


    setTheme(
        theme || "black"
    );
}


/* =========================================================
   SIDEBAR
========================================================= */

function toggleSidebar() {

    const sidebar =
        document.getElementById(
            "sidebar"
        );


    if (sidebar) {

        sidebar.classList.toggle(
            "open"
        );
    }
}


/* =========================================================
   SPECIAL AREAS
========================================================= */

function hideSpecialAreas() {

    [
        "imageArea",
        "websiteArea",
        "searchArea"
    ].forEach(
        id => {

            const element =
                document.getElementById(
                    id
                );


            if (element) {

                element.classList.add(
                    "hidden"
                );
            }
        }
    );
}


/* =========================================================
   LOGIN ERROR
========================================================= */

function showLoginError(
    message
) {

    const signIn =
        document.getElementById(
            "clerkSignIn"
        );


    if (!signIn) {
        return;
    }


    signIn.innerHTML = "";


    const wrapper =
        document.createElement(
            "div"
        );


    wrapper.style.padding =
        "20px";


    wrapper.style.textAlign =
        "center";


    wrapper.style.color =
        "#ff5555";


    wrapper.style.fontFamily =
        "Arial,sans-serif";


    wrapper.textContent =
        message;


    signIn.appendChild(
        wrapper
    );
}


/* =========================================================
   HTML ESCAPE
========================================================= */

function escapeHtml(
    text
) {

    const div =
        document.createElement(
            "div"
        );


    div.textContent =
        String(
            text ?? ""
        );


    return div.innerHTML;
}


/* =========================================================
   OUTSIDE CLICK
========================================================= */

document.addEventListener(
    "click",
    function(event) {

        const menu =
            document.getElementById(
                "themeMenu"
            );


        if (!menu) {
            return;
        }


        if (
            !menu.contains(
                event.target
            ) &&
            !event.target.closest(
                '[title="Theme"]'
            )
        ) {

            menu.classList.remove(
                "show"
            );
        }
    }
);
```
