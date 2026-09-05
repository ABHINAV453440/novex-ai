/* =========================================================
   NOVEX AI — COMPLETE SCRIPT
   Clerk + Chat + History + Image + Website + Search
   + PDF / FILE ATTACHMENT UI
   + STRONG CLERK AUTHENTICATION
   ========================================================= */

(() => {
  "use strict";

  /* =========================================================
     GLOBAL STATE
     ========================================================= */

  let clerkReady = false;
  let appStarted = false;
  let loginMounted = false;
  let loginWatcherStarted = false;
  let selectedFile = null;
  let isSending = false;

  const sleep = (ms) =>
    new Promise((resolve) => setTimeout(resolve, ms));

  /* =========================================================
     START
     ========================================================= */

  document.addEventListener("DOMContentLoaded", () => {
    initializeNovex();
    loadTheme();
    setupFileAttachment();
  });

  /* =========================================================
     CLERK INITIALIZATION
     ========================================================= */

  async function initializeNovex() {
    try {
      let attempts = 0;

      /* Wait for Clerk JS */
      while (
        typeof window.Clerk === "undefined" &&
        attempts < 200
      ) {
        await sleep(100);
        attempts++;
      }

      if (typeof window.Clerk === "undefined") {
        console.error("NOVEX: Clerk JS load nahi hua.");
        showLoginError("Clerk load nahi ho paya.");
        return;
      }

      /* Wait for Clerk UI initialization from index.html */
      attempts = 0;

      while (
        !window.__novexClerkReady &&
        attempts < 300
      ) {
        await sleep(100);
        attempts++;
      }

      if (!window.__novexClerkReady) {
        console.error(
          "NOVEX: Clerk UI initialization timeout."
        );

        showLoginError(
          "Login system start nahi ho paya."
        );

        return;
      }

      clerkReady = true;

      console.log("NOVEX: Clerk ready.");
      console.log(
        "NOVEX: Signed in =",
        Boolean(window.Clerk.isSignedIn)
      );

      /* Open app if already signed in */
      if (window.Clerk.isSignedIn) {
        await waitForClerkSession();
        await openNovexApp();
      } else {
        showLogin();
      }

      setupClerkListener();

    } catch (error) {
      console.error(
        "Clerk initialization error:",
        error
      );

      showLoginError(
        "Login system start nahi ho paya."
      );
    }
  }

  /* =========================================================
     WAIT FOR CLERK SESSION
     ========================================================= */

  async function waitForClerkSession() {
    let attempts = 0;

    while (
      attempts < 100 &&
      window.Clerk &&
      !window.Clerk.session
    ) {
      await sleep(100);
      attempts++;
    }

    if (window.Clerk && window.Clerk.session) {
      console.log("NOVEX: Clerk session ready.");
      return true;
    }

    console.warn(
      "NOVEX: Clerk session ready nahi hua."
    );

    return false;
  }

  /* =========================================================
     CLERK SESSION LISTENER
     ========================================================= */

  function setupClerkListener() {
    if (
      !window.Clerk ||
      typeof window.Clerk.addListener !== "function"
    ) {
      return;
    }

    window.Clerk.addListener(async (state) => {
      try {
        if (
          state &&
          state.session
        ) {
          await waitForClerkSession();
          await openNovexApp();
        } else if (
          window.Clerk.isSignedIn
        ) {
          await waitForClerkSession();
          await openNovexApp();
        } else {
          appStarted = false;
          loginMounted = false;
          showLogin();
        }
      } catch (error) {
        console.error(
          "Clerk listener error:",
          error
        );
      }
    });
  }

  /* =========================================================
     LOGIN
     ========================================================= */

  function showLogin() {
    const authScreen =
      document.getElementById("authScreen");

    const app =
      document.getElementById("app");

    const signIn =
      document.getElementById("clerkSignIn");

    if (!authScreen || !signIn) {
      return;
    }

    authScreen.classList.remove("hidden");

    if (app) {
      app.classList.add("hidden");
    }

    if (
      !loginMounted &&
      window.Clerk &&
      typeof window.Clerk.mountSignIn === "function"
    ) {
      try {
        signIn.innerHTML = "";

        window.Clerk.mountSignIn(signIn);

        loginMounted = true;

        console.log(
          "NOVEX: Clerk SignIn mounted."
        );

      } catch (error) {
        console.error(
          "Clerk SignIn error:",
          error
        );

        loginMounted = false;

        showLoginError(
          "Login screen load nahi ho paya. Page refresh karke try karo."
        );
      }
    }

    watchLogin();
  }

  function watchLogin() {
    if (loginWatcherStarted) {
      return;
    }

    loginWatcherStarted = true;

    const check = async () => {
      try {
        if (
          clerkReady &&
          window.Clerk &&
          window.Clerk.isSignedIn
        ) {
          await waitForClerkSession();
          await openNovexApp();
          return;
        }
      } catch (error) {
        console.error(
          "Login watcher error:",
          error
        );
      }

      setTimeout(check, 1000);
    };

    check();
  }

  /* =========================================================
     OPEN APP
     ========================================================= */

  async function openNovexApp() {
    if (
      !window.Clerk ||
      !window.Clerk.isSignedIn
    ) {
      showLogin();
      return;
    }

    if (appStarted) {
      return;
    }

    /* Make sure Clerk session exists */
    await waitForClerkSession();

    appStarted = true;

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

    try {
      await setupUser();
      await loadHistory();

      setupAppEvents();

      console.log(
        "NOVEX: App started successfully."
      );

    } catch (error) {
      console.error(
        "App startup error:",
        error
      );

      /*
        If startup auth fails, don't permanently
        lock the application.
      */
      appStarted = false;
    }
  }

  /* =========================================================
     USER
     ========================================================= */

  async function setupUser() {
    try {
      const response =
        await authFetch("/api/me");

      if (!response.ok) {
        throw new Error(
          `User API failed: ${response.status}`
        );
      }

      const data =
        await response.json();

      const username =
        data?.user?.username ||
        data?.user?.firstName ||
        data?.user?.email ||
        "User";

      const loggedUsername =
        document.getElementById(
          "loggedUsername"
        );

      if (loggedUsername) {
        loggedUsername.textContent =
          username;
      }

      const avatar =
        document.getElementById(
          "userAvatar"
        );

      if (avatar) {
        avatar.textContent =
          String(username)
            .charAt(0)
            .toUpperCase();
      }

    } catch (error) {
      console.error(
        "setupUser error:",
        error
      );

      const loggedUsername =
        document.getElementById(
          "loggedUsername"
        );

      if (loggedUsername) {
        loggedUsername.textContent =
          "User";
      }
    }
  }

  /* =========================================================
     GET CLERK AUTH TOKEN
     ========================================================= */

  async function getAuthToken(forceRefresh = false) {
    try {
      if (
        !window.Clerk ||
        !window.Clerk.session ||
        typeof window.Clerk.session.getToken !==
          "function"
      ) {
        console.warn(
          "NOVEX: Clerk session/token unavailable."
        );

        return null;
      }

      const options = forceRefresh
        ? { skipCache: true }
        : {};

      const token =
        await window.Clerk.session.getToken(
          options
        );

      if (!token) {
        console.warn(
          "NOVEX: Clerk token empty."
        );

        return null;
      }

      return token;

    } catch (error) {
      console.error(
        "NOVEX token error:",
        error
      );

      return null;
    }
  }

  /* =========================================================
     AUTHENTICATED FETCH
     ========================================================= */

  async function authFetch(
    url,
    options = {},
    retry = true
  ) {
    try {
      /*
        Make sure Clerk is ready.
      */
      if (
        !window.Clerk ||
        !window.Clerk.isSignedIn
      ) {
        throw new Error(
          "User is not signed in."
        );
      }

      await waitForClerkSession();

      /*
        Get current Clerk session token.
      */
      let token =
        await getAuthToken(false);

      /*
        If token is unavailable, wait and retry
        token generation once.
      */
      if (!token) {
        await sleep(500);
        token =
          await getAuthToken(true);
      }

      const headers =
        new Headers(
          options.headers || {}
        );

      /*
        IMPORTANT:
        Send Clerk session token to Express.
      */
      if (token) {
        headers.set(
          "Authorization",
          `Bearer ${token}`
        );
      }

      /*
        Automatically set JSON header
        when body exists.
      */
      if (
        options.body &&
        !headers.has("Content-Type")
      ) {
        headers.set(
          "Content-Type",
          "application/json"
        );
      }

      /*
        Credentials are also included for Clerk
        cookie/session support.
      */
      const response =
        await fetch(url, {
          ...options,
          headers,
          credentials: "include"
        });

      /*
        If backend says 401, get a fresh Clerk token
        and retry the exact request once.
      */
      if (
        response.status === 401 &&
        retry
      ) {
        console.warn(
          "NOVEX: 401 received. Refreshing Clerk token..."
        );

        const freshToken =
          await getAuthToken(true);

        if (freshToken) {
          const retryHeaders =
            new Headers(
              options.headers || {}
            );

          retryHeaders.set(
            "Authorization",
            `Bearer ${freshToken}`
          );

          if (
            options.body &&
            !retryHeaders.has(
              "Content-Type"
            )
          ) {
            retryHeaders.set(
              "Content-Type",
              "application/json"
            );
          }

          return fetch(url, {
            ...options,
            headers: retryHeaders,
            credentials: "include"
          });
        }
      }

      return response;

    } catch (error) {
      console.error(
        "NOVEX authFetch error:",
        error
      );

      throw error;
    }
  }

  /* =========================================================
     CHAT
     ========================================================= */

  async function sendMessage() {
    const input =
      document.getElementById(
        "messageInput"
      ) ||
      document.getElementById(
        "userInput"
      );

    if (!input) {
      return;
    }

    if (isSending) {
      return;
    }

    const message =
      input.value.trim();

    if (
      !message &&
      !selectedFile
    ) {
      return;
    }

    isSending = true;

    const fileAtSendTime =
      selectedFile;

    input.value = "";

    autoResize(input);

    let displayMessage =
      message;

    if (fileAtSendTime) {
      displayMessage =
        message
          ? `${message}\n\n📎 ${fileAtSendTime.name}`
          : `📎 ${fileAtSendTime.name}`;
    }

    addMessage(
      displayMessage,
      "user"
    );

    showTyping();

    try {
      const response =
        await authFetch(
          "/api/chat",
          {
            method: "POST",
            body: JSON.stringify({
              message
            })
          }
        );

      hideTyping();

      if (!response.ok) {
        let errorMessage =
          `AI request failed: ${response.status}`;

        try {
          const errorData =
            await response.json();

          if (errorData?.error) {
            errorMessage =
              errorData.error;
          }
        } catch (_) {}

        throw new Error(
          errorMessage
        );
      }

      const data =
        await response.json();

      const answer =
        data.reply ||
        data.message ||
        data.response ||
        "Sorry, mujhe response nahi mila.";

      addMessage(
        answer,
        "ai"
      );

      await loadHistory();

      if (fileAtSendTime) {
        clearSelectedFile();
      }

    } catch (error) {
      hideTyping();

      console.error(
        "Chat error:",
        error
      );

      addMessage(
        "⚠️ AI response nahi aa raha. Thodi der baad dobara try karo.",
        "ai"
      );

      showToast(
        "AI request failed"
      );

    } finally {
      isSending = false;
    }
  }

  /* =========================================================
     ASK AI
     ========================================================= */

  async function askAI(message) {
    if (!message) {
      return "";
    }

    try {
      const response =
        await authFetch(
          "/api/chat",
          {
            method: "POST",
            body: JSON.stringify({
              message
            })
          }
        );

      if (!response.ok) {
        throw new Error(
          `AI request failed: ${response.status}`
        );
      }

      const data =
        await response.json();

      return (
        data.reply ||
        data.message ||
        data.response ||
        ""
      );

    } catch (error) {
      console.error(
        "askAI error:",
        error
      );

      return "";
    }
  }

  /* =========================================================
     MESSAGE UI
     ========================================================= */

  function addMessage(
    text,
    type = "ai"
  ) {
    const messages =
      document.getElementById(
        "messages"
      );

    if (!messages) {
      return;
    }

    const welcome =
      document.getElementById(
        "welcomeScreen"
      );

    if (welcome) {
      welcome.classList.add(
        "hidden"
      );
    }

    const messageDiv =
      document.createElement(
        "div"
      );

    messageDiv.className =
      `message ${
        type === "user"
          ? "user"
          : "ai"
      }`;

    const content =
      document.createElement(
        "div"
      );

    content.className =
      "message-content";

    content.innerHTML =
      formatAIText(text);

    messageDiv.appendChild(
      content
    );

    messages.appendChild(
      messageDiv
    );

    messages.scrollTop =
      messages.scrollHeight;
  }

  /* =========================================================
     FORMAT AI TEXT
     ========================================================= */

  function formatAIText(text) {
    if (!text) {
      return "";
    }

    let safe =
      escapeHTML(
        String(text)
      );

    /*
      Code blocks
    */
    safe = safe.replace(
      /```([\s\S]*?)```/g,
      "<pre><code>$1</code></pre>"
    );

    /*
      Bold
    */
    safe = safe.replace(
      /\*\*(.*?)\*\*/g,
      "<strong>$1</strong>"
    );

    /*
      Inline code
    */
    safe = safe.replace(
      /`([^`]+)`/g,
      "<code>$1</code>"
    );

    /*
      New lines
    */
    safe = safe.replace(
      /\n/g,
      "<br>"
    );

    return safe;
  }

  function escapeHTML(text) {
    const div =
      document.createElement(
        "div"
      );

    div.textContent =
      text;

    return div.innerHTML;
  }

  /* =========================================================
     TYPING
     ========================================================= */

  function showTyping() {
    hideTyping();

    const messages =
      document.getElementById(
        "messages"
      );

    if (!messages) {
      return;
    }

    const typing =
      document.createElement(
        "div"
      );

    typing.id =
      "novexTyping";

    typing.className =
      "message ai";

    typing.innerHTML = `
      <div class="message-content">
        <span class="typing-dot">●</span>
        <span class="typing-dot">●</span>
        <span class="typing-dot">●</span>
      </div>
    `;

    messages.appendChild(
      typing
    );

    messages.scrollTop =
      messages.scrollHeight;
  }

  function hideTyping() {
    const typing =
      document.getElementById(
        "novexTyping"
      );

    if (typing) {
      typing.remove();
    }
  }

  /* =========================================================
     HISTORY
     ========================================================= */

  async function loadHistory() {
    const historyList =
      document.getElementById(
        "historyList"
      );

    if (!historyList) {
      return;
    }

    try {
      const response =
        await authFetch(
          "/api/history"
        );

      if (!response.ok) {
        console.warn(
          "History request failed:",
          response.status
        );
        return;
      }

      const data =
        await response.json();

      const history =
        Array.isArray(data)
          ? data
          : data.history || [];

      historyList.innerHTML =
        "";

      history.forEach(
        (item, index) => {
          const title =
            item.title ||
            item.message ||
            item.prompt ||
            "New Chat";

          const div =
            document.createElement(
              "div"
            );

          div.className =
            "history-item";

          div.innerHTML = `
            <span>
              ${escapeHTML(
                String(title)
                  .slice(0, 40)
              )}
            </span>

            <button
              class="history-delete"
              data-index="${index}"
              type="button"
              title="Delete chat"
              aria-label="Delete chat"
            >
              ×
            </button>
          `;

          div.addEventListener(
            "click",
            (event) => {
              if (
                event.target.classList.contains(
                  "history-delete"
                )
              ) {
                return;
              }

              restoreHistoryItem(
                item
              );
            }
          );

          const deleteButton =
            div.querySelector(
              ".history-delete"
            );

          if (deleteButton) {
            deleteButton.addEventListener(
              "click",
              async (event) => {
                event.stopPropagation();

                await deleteHistory(
                  index
                );
              }
            );
          }

          historyList.appendChild(
            div
          );
        }
      );

    } catch (error) {
      console.error(
        "History error:",
        error
      );
    }
  }

  /* =========================================================
     RESTORE HISTORY
     ========================================================= */

  function restoreHistoryItem(
    item
  ) {
    const messages =
      document.getElementById(
        "messages"
      );

    if (!messages) {
      return;
    }

    messages.innerHTML =
      "";

    const welcome =
      document.getElementById(
        "welcomeScreen"
      );

    if (welcome) {
      welcome.classList.add(
        "hidden"
      );
    }

    if (item.message) {
      addMessage(
        item.message,
        "user"
      );
    }

    if (item.reply) {
      addMessage(
        item.reply,
        "ai"
      );
    } else if (
      item.response
    ) {
      addMessage(
        item.response,
        "ai"
      );
    }
  }

  /* =========================================================
     DELETE HISTORY
     ========================================================= */

  async function deleteHistory(
    index
  ) {
    try {
      const response =
        await authFetch(
          `/api/history/${index}`,
          {
            method: "DELETE"
          }
        );

      if (!response.ok) {
        throw new Error(
          "Delete failed"
        );
      }

      await loadHistory();

      showToast(
        "Chat deleted"
      );

    } catch (error) {
      console.error(
        "Delete history error:",
        error
      );

      showToast(
        "Delete failed"
      );
    }
  }

  /* =========================================================
     CLEAR ALL
     ========================================================= */

  async function clearHistory() {
    try {
      const response =
        await authFetch(
          "/api/history",
          {
            method: "DELETE"
          }
        );

      if (!response.ok) {
        throw new Error(
          "Clear failed"
        );
      }

      const messages =
        document.getElementById(
          "messages"
        );

      if (messages) {
        messages.innerHTML =
          "";
      }

      const welcome =
        document.getElementById(
          "welcomeScreen"
        );

      if (welcome) {
        welcome.classList.remove(
          "hidden"
        );
      }

      hideSpecialAreas();

      await loadHistory();

      showToast(
        "All history cleared"
      );

    } catch (error) {
      console.error(
        "Clear history error:",
        error
      );

      showToast(
        "History clear nahi hua"
      );
    }
  }

  /* =========================================================
     NEW CHAT
     ========================================================= */

  function newChat() {
    const messages =
      document.getElementById(
        "messages"
      );

    if (messages) {
      messages.innerHTML =
        "";
    }

    const welcome =
      document.getElementById(
        "welcomeScreen"
      );

    if (welcome) {
      welcome.classList.remove(
        "hidden"
      );
    }

    hideSpecialAreas();

    clearSelectedFile();

    const input =
      document.getElementById(
        "messageInput"
      ) ||
      document.getElementById(
        "userInput"
      );

    if (input) {
      input.value =
        "";

      autoResize(input);

      input.focus();
    }
  }

  /* =========================================================
     IMAGE GENERATION
     ========================================================= */

  async function generateImage(
    prompt
  ) {
    if (!prompt) {
      showToast(
        "Image prompt likho"
      );
      return;
    }

    const imageArea =
      document.getElementById(
        "imageArea"
      );

    if (imageArea) {
      imageArea.classList.remove(
        "hidden"
      );

      imageArea.innerHTML = `
        <div class="special-loading">
          🎨 Image generate ho rahi hai...
        </div>
      `;
    }

    try {
      if (
        window.puter &&
        window.puter.ai &&
        typeof window.puter.ai.txt2img ===
          "function"
      ) {
        const result =
          await window.puter.ai.txt2img(
            prompt
          );

        if (imageArea) {
          imageArea.innerHTML =
            "";

          if (result) {
            const img =
              document.createElement(
                "img"
              );

            if (
              typeof result ===
              "string"
            ) {
              img.src =
                result;
            } else if (
              result.src
            ) {
              img.src =
                result.src;
            } else if (
              result.url
            ) {
              img.src =
                result.url;
            }

            img.alt =
              String(prompt);

            imageArea.appendChild(
              img
            );

          } else {
            imageArea.innerHTML =
              "<p>Image generate nahi hui.</p>";
          }
        }

        return;
      }

      throw new Error(
        "Puter AI unavailable"
      );

    } catch (error) {
      console.error(
        "Image error:",
        error
      );

      if (imageArea) {
        imageArea.innerHTML = `
          <div class="special-error">
            ⚠️ Image generation failed.
          </div>
        `;
      }

      showToast(
        "Image generation failed"
      );
    }
  }

  /* =========================================================
     WEBSITE GENERATOR
     ========================================================= */

  async function generateWebsite(
    prompt
  ) {
    if (!prompt) {
      showToast(
        "Website idea likho"
      );
      return;
    }

    const websiteArea =
      document.getElementById(
        "websiteArea"
      );

    if (websiteArea) {
      websiteArea.classList.remove(
        "hidden"
      );

      websiteArea.innerHTML = `
        <div class="special-loading">
          🌐 Website generate ho rahi hai...
        </div>
      `;
    }

    try {
      const result =
        await askAI(`
Create a complete modern website based on this idea:

${prompt}

Return clean HTML, CSS and JavaScript.

Make it responsive and professional.
`);

      if (!result) {
        throw new Error(
          "No website response"
        );
      }

      if (websiteArea) {
        websiteArea.innerHTML = `
          <div class="website-result">
            <h3>
              🌐 Generated Website Code
            </h3>

            <pre><code>${escapeHTML(
              result
            )}</code></pre>
          </div>
        `;
      }

    } catch (error) {
      console.error(
        "Website error:",
        error
      );

      if (websiteArea) {
        websiteArea.innerHTML = `
          <div class="special-error">
            ⚠️ Website generation failed.
          </div>
        `;
      }
    }
  }

  /* =========================================================
     WEB SEARCH
     ========================================================= */

  async function searchWeb(
    query
  ) {
    if (!query) {
      showToast(
        "Search query likho"
      );
      return;
    }

    const searchArea =
      document.getElementById(
        "searchArea"
      );

    if (searchArea) {
      searchArea.classList.remove(
        "hidden"
      );

      searchArea.innerHTML = `
        <div class="special-loading">
          🔎 Searching...
        </div>
      `;
    }

    try {
      const response =
        await authFetch(
          "/api/search-ai",
          {
            method: "POST",
            body: JSON.stringify({
              query
            })
          }
        );

      if (!response.ok) {
        throw new Error(
          `Search failed: ${response.status}`
        );
      }

      const data =
        await response.json();

      const result =
        data.answer ||
        data.reply ||
        data.response ||
        data.results ||
        "No result found.";

      if (searchArea) {
        searchArea.innerHTML = `
          <div class="search-result">
            ${formatAIText(
              typeof result ===
                "string"
                ? result
                : JSON.stringify(
                    result,
                    null,
                    2
                  )
            )}
          </div>
        `;
      }

    } catch (error) {
      console.error(
        "Search error:",
        error
      );

      if (searchArea) {
        searchArea.innerHTML = `
          <div class="special-error">
            ⚠️ Search failed.
          </div>
        `;
      }
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
    ].forEach((id) => {
      const element =
        document.getElementById(
          id
        );

      if (element) {
        element.classList.add(
          "hidden"
        );

        element.innerHTML =
          "";
      }
    });
  }

  /* =========================================================
     INPUT
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
      Math.min(
        textarea.scrollHeight,
        180
      ) + "px";
  }

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
     PDF / FILE ATTACHMENT
     ========================================================= */

  function setupFileAttachment() {
    const fileInput =
      document.getElementById(
        "fileInput"
      );

    const removeButton =
      document.getElementById(
        "removeSelectedFile"
      );

    if (!fileInput) {
      return;
    }

    if (
      fileInput.dataset.novexBound
    ) {
      return;
    }

    fileInput.dataset.novexBound =
      "true";

    fileInput.addEventListener(
      "change",
      () => {
        const file =
          fileInput.files &&
          fileInput.files[0];

        if (!file) {
          return;
        }

        handleSelectedFile(
          file
        );
      }
    );

    if (removeButton) {
      removeButton.addEventListener(
        "click",
        (event) => {
          event.preventDefault();
          event.stopPropagation();

          clearSelectedFile();
        }
      );
    }
  }

  function handleSelectedFile(
    file
  ) {
    const maxSize =
      10 * 1024 * 1024;

    if (file.size > maxSize) {
      showToast(
        "File 10MB se chhoti honi chahiye."
      );

      clearSelectedFile();

      return;
    }

    const allowedTypes = [
      "application/pdf",
      "text/plain",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "image/jpeg",
      "image/png",
      "image/webp"
    ];

    const extension =
      file.name
        .split(".")
        .pop()
        .toLowerCase();

    const allowedExtensions = [
      "pdf",
      "txt",
      "doc",
      "docx",
      "jpg",
      "jpeg",
      "png",
      "webp"
    ];

    if (
      !allowedTypes.includes(
        file.type
      ) &&
      !allowedExtensions.includes(
        extension
      )
    ) {
      showToast(
        "Ye file type supported nahi hai."
      );

      clearSelectedFile();

      return;
    }

    selectedFile =
      file;

    const selectedFileBox =
      document.getElementById(
        "selectedFile"
      );

    const selectedFileName =
      document.getElementById(
        "selectedFileName"
      );

    if (
      selectedFileBox &&
      selectedFileName
    ) {
      selectedFileName.textContent =
        file.name;

      selectedFileBox.classList.remove(
        "hidden"
      );
    }

    showToast(
      `📎 ${file.name} attached`
    );
  }

  function clearSelectedFile() {
    selectedFile =
      null;

    const fileInput =
      document.getElementById(
        "fileInput"
      );

    const selectedFileBox =
      document.getElementById(
        "selectedFile"
      );

    const selectedFileName =
      document.getElementById(
        "selectedFileName"
      );

    if (fileInput) {
      fileInput.value =
        "";
    }

    if (selectedFileBox) {
      selectedFileBox.classList.add(
        "hidden"
      );
    }

    if (selectedFileName) {
      selectedFileName.textContent =
        "File";
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
      showToast(
        "Is browser me voice input supported nahi hai."
      );

      return;
    }

    const recognition =
      new SpeechRecognition();

    recognition.lang =
      "hi-IN";

    recognition.interimResults =
      false;

    recognition.maxAlternatives =
      1;

    recognition.onstart =
      () => {
        showToast(
          "🎤 Listening..."
        );
      };

    recognition.onresult =
      (event) => {
        const text =
          event.results[0][0]
            .transcript;

        const input =
          document.getElementById(
            "messageInput"
          ) ||
          document.getElementById(
            "userInput"
          );

        if (input) {
          input.value +=
            (input.value
              ? " "
              : "") + text;

          autoResize(input);
        }
      };

    recognition.onerror =
      (event) => {
        console.error(
          "Voice error:",
          event.error
        );

        showToast(
          "Voice input failed"
        );
      };

    recognition.start();
  }

  /* =========================================================
     THEME
     ========================================================= */

  function loadTheme() {
    const theme =
      localStorage.getItem(
        "novex-theme"
      );

    if (theme === "light") {
      document.body.classList.add(
        "light-theme"
      );
    }
  }

  function toggleTheme() {
    document.body.classList.toggle(
      "light-theme"
    );

    const isLight =
      document.body.classList.contains(
        "light-theme"
      );

    localStorage.setItem(
      "novex-theme",
      isLight
        ? "light"
        : "dark"
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

    if (!sidebar) {
      return;
    }

    if (
      window.innerWidth <= 800
    ) {
      sidebar.classList.toggle(
        "open"
      );
    } else {
      sidebar.classList.toggle(
        "collapsed"
      );
    }
  }

  /* =========================================================
     APP EVENTS
     ========================================================= */

  function setupAppEvents() {
    const input =
      document.getElementById(
        "messageInput"
      ) ||
      document.getElementById(
        "userInput"
      );

    if (
      input &&
      !input.dataset.novexBound
    ) {
      input.dataset.novexBound =
        "true";

      input.addEventListener(
        "input",
        () => {
          autoResize(input);
        }
      );

      input.addEventListener(
        "keydown",
        handleKeyPress
      );

      autoResize(input);
    }

    const themeButton =
      document.getElementById(
        "themeToggle"
      );

    if (
      themeButton &&
      !themeButton.dataset.novexBound
    ) {
      themeButton.dataset.novexBound =
        "true";

      themeButton.addEventListener(
        "click",
        toggleTheme
      );
    }
  }

  /* =========================================================
     TOAST
     ========================================================= */

  function showToast(message) {
    let toast =
      document.getElementById(
        "novexToast"
      );

    if (!toast) {
      toast =
        document.createElement(
          "div"
        );

      toast.id =
        "novexToast";

      document.body.appendChild(
        toast
      );
    }

    toast.textContent =
      message;

    toast.classList.add(
      "show"
    );

    clearTimeout(
      window.__novexToastTimer
    );

    window.__novexToastTimer =
      setTimeout(() => {
        toast.classList.remove(
          "show"
        );
      }, 2500);
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

    signIn.innerHTML = `
      <div class="auth-error">
        ⚠️ ${escapeHTML(message)}
      </div>
    `;
  }

  /* =========================================================
     WINDOW RESIZE
     ========================================================= */

  window.addEventListener(
    "resize",
    () => {
      const sidebar =
        document.getElementById(
          "sidebar"
        );

      if (
        sidebar &&
        window.innerWidth > 800
      ) {
        sidebar.classList.remove(
          "open"
        );
      }
    }
  );

  /* =========================================================
     GLOBAL FUNCTIONS
     ========================================================= */

  window.sendMessage =
    sendMessage;

  window.askAI =
    askAI;

  window.newChat =
    newChat;

  window.generateImage =
    generateImage;

  window.generateWebsite =
    generateWebsite;

  window.searchWeb =
    searchWeb;

  window.startVoiceInput =
    startVoiceInput;

  window.handleKeyPress =
    handleKeyPress;

  window.autoResize =
    autoResize;

  window.toggleTheme =
    toggleTheme;

  window.toggleSidebar =
    toggleSidebar;

  window.clearHistory =
    clearHistory;

  window.clearSelectedFile =
    clearSelectedFile;

  /*
    Debug helpers — useful from browser console.
  */
  window.NOVEX_AUTH_TEST =
    async function () {
      const token =
        await getAuthToken(true);

      console.log(
        "NOVEX AUTH TEST:",
        {
          clerkExists:
            Boolean(window.Clerk),

          signedIn:
            Boolean(
              window.Clerk?.isSignedIn
            ),

          sessionExists:
            Boolean(
              window.Clerk?.session
            ),

          tokenExists:
            Boolean(token),

          tokenLength:
            token
              ? token.length
              : 0
        }
      );

      return Boolean(token);
    };

})();