/* =========================================================
   NOVEX AI
   LOGIN + SMART AI
========================================================= */

let chats = [];
let currentChat = null;

let authToken =
  localStorage.getItem(
    "novex_auth_token"
  ) || "";

let currentUser = null;


/* =========================================================
   START
========================================================= */

document.addEventListener(
  "DOMContentLoaded",
  async () => {

    loadTheme();

    await checkLogin();

  }
);


/* =========================================================
   AUTH CHECK
========================================================= */

async function checkLogin() {

  if (!authToken) {

    showAuth();

    return;

  }


  try {

    const response =
      await fetch(
        "/api/me",
        {
          headers: {
            Authorization:
              `Bearer ${authToken}`
          }
        }
      );


    const data =
      await response.json();


    if (
      !response.ok ||
      !data.success
    ) {

      throw new Error(
        "Session expired"
      );

    }


    currentUser =
      data.user;


    await enterApp();

  }

  catch {

    localStorage.removeItem(
      "novex_auth_token"
    );

    authToken = "";

    showAuth();

  }

}


/* =========================================================
   SHOW AUTH
========================================================= */

function showAuth() {

  const auth =
    document.getElementById(
      "authScreen"
    );

  const app =
    document.getElementById(
      "app"
    );


  auth.classList.remove(
    "hidden"
  );

  app.classList.add(
    "hidden"
  );

}


/* =========================================================
   SHOW APP
========================================================= */

async function enterApp() {

  document
    .getElementById(
      "authScreen"
    )
    .classList.add(
      "hidden"
    );


  document
    .getElementById(
      "app"
    )
    .classList.remove(
      "hidden"
    );


  document
    .getElementById(
      "loggedUsername"
    )
    .textContent =
    currentUser.username;


  await loadServerHistory();


  if (!currentChat) {

    createNewLocalChat();

  }


  renderHistory();

  renderMessages();


}


/* =========================================================
   LOGIN
========================================================= */

async function loginUser() {

  const username =
    document
      .getElementById(
        "loginUsername"
      )
      .value
      .trim();


  const password =
    document
      .getElementById(
        "loginPassword"
      )
      .value;


  const errorBox =
    document
      .getElementById(
        "loginError"
      );


  errorBox.textContent =
    "";


  if (!username || !password) {

    errorBox.textContent =
      "Username aur password enter karo.";

    return;

  }


  try {

    const response =
      await fetch(
        "/api/login",
        {

          method:
            "POST",

          headers: {
            "Content-Type":
              "application/json"
          },

          body:
            JSON.stringify({
              username,
              password
            })

        }
      );


    const data =
      await response.json();


    if (
      !response.ok ||
      !data.success
    ) {

      throw new Error(
        data.error ||
        "Login failed"
      );

    }


    authToken =
      data.token;


    currentUser =
      data.user;


    localStorage.setItem(
      "novex_auth_token",
      authToken
    );


    document
      .getElementById(
        "loginPassword"
      )
      .value = "";


    await enterApp();


    showToast(
      `Welcome ${currentUser.username} 👋`
    );

  }

  catch (error) {

    errorBox.textContent =
      error.message;

  }

}


/* =========================================================
   SIGNUP
========================================================= */

async function signupUser() {

  const username =
    document
      .getElementById(
        "signupUsername"
      )
      .value
      .trim();


  const password =
    document
      .getElementById(
        "signupPassword"
      )
      .value;


  const password2 =
    document
      .getElementById(
        "signupPassword2"
      )
      .value;


  const errorBox =
    document
      .getElementById(
        "signupError"
      );


  errorBox.textContent =
    "";


  if (
    !username ||
    !password ||
    !password2
  ) {

    errorBox.textContent =
      "Sabhi fields fill karo.";

    return;

  }


  if (
    password !==
    password2
  ) {

    errorBox.textContent =
      "Passwords match nahi karte.";

    return;

  }


  if (
    password.length < 6
  ) {

    errorBox.textContent =
      "Password minimum 6 characters ka hona chahiye.";

    return;

  }


  try {

    const response =
      await fetch(
        "/api/signup",
        {

          method:
            "POST",

          headers: {
            "Content-Type":
              "application/json"
          },

          body:
            JSON.stringify({
              username,
              password
            })

        }
      );


    const data =
      await response.json();


    if (
      !response.ok ||
      !data.success
    ) {

      throw new Error(
        data.error ||
        "Signup failed"
      );

    }


    authToken =
      data.token;


    currentUser =
      data.user;


    localStorage.setItem(
      "novex_auth_token",
      authToken
    );


    document
      .getElementById(
        "signupPassword"
      )
      .value = "";


    document
      .getElementById(
        "signupPassword2"
      )
      .value = "";


    await enterApp();


    showToast(
      "Account created 🎉"
    );

  }

  catch (error) {

    errorBox.textContent =
      error.message;

  }

}


/* =========================================================
   AUTH SWITCH
========================================================= */

function showSignup() {

  document
    .getElementById(
      "loginPanel"
    )
    .classList.add(
      "hidden"
    );


  document
    .getElementById(
      "signupPanel"
    )
    .classList.remove(
      "hidden"
    );

}


function showLogin() {

  document
    .getElementById(
      "signupPanel"
    )
    .classList.add(
      "hidden"
    );


  document
    .getElementById(
      "loginPanel"
    )
    .classList.remove(
      "hidden"
    );

}


/* =========================================================
   LOGOUT
========================================================= */

async function logoutUser() {

  const confirmed =
    confirm(
      "Logout karna hai?"
    );


  if (!confirmed) {
    return;
  }


  try {

    await fetch(
      "/api/logout",
      {

        method:
          "POST",

        headers: {

          Authorization:
            `Bearer ${authToken}`

        }

      }
    );

  }

  catch {
    /* local logout continues */
  }


  localStorage.removeItem(
    "novex_auth_token"
  );


  authToken = "";

  currentUser = null;

  chats = [];

  currentChat = null;


  showAuth();


  showLogin();


  showToast(
    "Logged out"
  );

}


/* =========================================================
   HISTORY FROM SERVER
========================================================= */

async function loadServerHistory() {

  try {

    const response =
      await fetch(
        "/api/history",
        {

          headers: {

            Authorization:
              `Bearer ${authToken}`

          }

        }
      );


    const data =
      await response.json();


    if (
      !response.ok ||
      !data.success
    ) {

      throw new Error(
        data.error ||
        "History load failed"
      );

    }


    chats =
      Array.isArray(
        data.chats
      )
        ? data.chats
        : [];


    currentChat =
      chats.length
        ? chats[0]
        : null;


  }

  catch (error) {

    console.error(
      "History load error:",
      error
    );


    chats = [];

    currentChat = null;

  }

}


/* =========================================================
   SAVE HISTORY
========================================================= */

async function saveHistory() {

  try {

    localStorage.setItem(
      "novex_local_backup",
      JSON.stringify(chats)
    );


    if (!authToken) {
      return;
    }


    await fetch(
      "/api/history",
      {

        method:
          "POST",

        headers: {

          "Content-Type":
            "application/json",

          Authorization:
            `Bearer ${authToken}`

        },

        body:
          JSON.stringify({
            chats
          })

      }
    );

  }

  catch (error) {

    console.error(
      "History save error:",
      error
    );

  }

}


/* =========================================================
   CREATE CHAT
========================================================= */

function createNewLocalChat() {

  currentChat = {

    id:
      Date.now(),

    title:
      "New Chat",

    messages: []

  };


  chats.unshift(
    currentChat
  );

}


function newChat() {

  createNewLocalChat();


  saveHistory();

  renderHistory();

  renderMessages();

  resetSpecialAreas();


  const welcome =
    document.getElementById(
      "welcome"
    );


  if (welcome) {

    welcome.style.display =
      "block";

  }


  const input =
    document.getElementById(
      "userInput"
    );


  if (input) {

    input.value = "";

    input.style.height =
      "auto";

    input.focus();

  }


  setStatus(
    "Ready to help"
  );

}


/* =========================================================
   SEND
========================================================= */

function sendMessage() {

  if (!currentUser) {

    showAuth();

    return;

  }


  const input =
    document.getElementById(
      "userInput"
    );


  const text =
    input.value.trim();


  if (!text) {
    return;
  }


  input.value = "";

  autoResize(input);

  resetSpecialAreas();


  addMessage(
    "user",
    text
  );


  routeRequest(text);

}


/* =========================================================
   SMART ROUTER
========================================================= */

async function routeRequest(text) {

  setStatus(
    "Understanding your question..."
  );


  const lower =
    text.toLowerCase().trim();


  /* IMAGE */

  const imagePatterns = [

    "generate image",
    "create image",
    "make image",
    "draw image",
    "create a picture",
    "generate a picture",
    "make a picture",
    "image banao",
    "photo banao",
    "picture banao",
    "image bana",
    "photo bana",
    "tasveer banao",
    "तस्वीर बनाओ",
    "चित्र बनाओ",
    "इमेज बनाओ",
    "फोटो बनाओ"

  ];


  if (
    imagePatterns.some(
      pattern =>
        lower.includes(pattern)
    )
  ) {

    await generateImage(text);

    return;

  }


  /* WEBSITE */

  const websitePatterns = [

    "website banao",
    "website bana",
    "website create",
    "create website",
    "build website",
    "make website",
    "webpage banao",
    "landing page banao",
    "site banao",
    "html css website",
    "portfolio website",
    "वेबसाइट बनाओ",
    "वेबसाइट बनाना"

  ];


  if (
    websitePatterns.some(
      pattern =>
        lower.includes(pattern)
    )
  ) {

    await generateWebsite(
      text
    );

    return;

  }


  /* SEARCH */

  const explicitSearchPatterns = [

    "search this",
    "search web",
    "search the web",
    "google this",
    "find online",
    "internet par search",
    "web par search",
    "online search",
    "internet se batao",
    "वेब पर खोजो",
    "इंटरनेट पर खोजो"

  ];


  if (
    explicitSearchPatterns.some(
      pattern =>
        lower.includes(pattern)
    )
  ) {

    await webSearch(text);

    return;

  }


  /* CURRENT */

  if (
    needsCurrentInformation(text)
  ) {

    await webSearch(text);

    return;

  }


  /* CODING */

  const codingPatterns = [

    "write code",
    "give code",
    "code banao",
    "code bana",
    "coding",
    "program banao",
    "program bana",
    "programming",
    "python",
    "javascript",
    "typescript",
    "java code",
    "c++",
    "html code",
    "css code",
    "node.js",
    "nodejs",
    "react",
    "api banao",
    "api bana",
    "bug fix",
    "debug",
    "debug karo",
    "error fix",
    "function banao",
    "कोड बनाओ",
    "प्रोग्राम बनाओ",
    "कोड लिखो"

  ];


  if (
    codingPatterns.some(
      pattern =>
        lower.includes(pattern)
    )
  ) {

    await askAI(`

You are Novex Coding AI.

USER REQUEST:
${text}

Give practical and working code.

Rules:
- Keep the answer concise.
- Give code first.
- Then give a short explanation.

`);

    return;

  }


  /* MATH */

  const mathPatterns = [

    "solve",
    "calculate",
    "calculator",
    "equation",
    "algebra",
    "geometry",
    "trigonometry",
    "derivative",
    "integral",
    "percentage",
    "math",
    "mathematics",
    "गणित",
    "हल करो",
    "समीकरण",
    "प्रतिशत"

  ];


  const hasMathExpression =
    /\d+\s*[\+\-\*\/=^]\s*\d+/.test(
      text
    ) ||
    /[xy]\s*[\+\-\*\/=^]/i.test(
      text
    );


  if (
    mathPatterns.some(
      pattern =>
        lower.includes(pattern)
    ) ||
    hasMathExpression
  ) {

    await askAI(`

You are Novex Math AI.

USER PROBLEM:
${text}

Rules:
- Solve step-by-step.
- Keep it concise.
- Show only necessary calculations.
- Give the final answer clearly.

`);

    return;

  }


  /* STUDY */

  const studyPatterns = [

    "bihar board",
    "class 10",
    "class 9",
    "class 8",
    "board exam",
    "chapter",
    "mcq",
    "question answer",
    "important question",
    "notes",
    "revision",
    "study",
    "homework",
    "physics",
    "chemistry",
    "biology",
    "history",
    "geography",
    "civics",
    "economics",
    "पढ़ाई",
    "पढ़ाई",
    "अध्याय",
    "नोट्स",
    "प्रश्न उत्तर",
    "महत्वपूर्ण प्रश्न",
    "बिहार बोर्ड"

  ];


  if (
    studyPatterns.some(
      pattern =>
        lower.includes(pattern)
    )
  ) {

    await askAI(`

You are Novex Study AI.

USER QUESTION:
${text}

Rules:
- Explain clearly.
- Use simple Hindi/Hinglish.
- Make the answer exam-friendly.
- Keep it concise unless detail is requested.

`);

    return;

  }


  /* WRITING */

  const writingPatterns = [

    "write a",
    "write an",
    "rewrite",
    "essay",
    "letter",
    "application",
    "story",
    "paragraph",
    "email",
    "script",
    "caption",
    "bio",
    "poem",
    "निबंध",
    "पत्र",
    "आवेदन",
    "कहानी",
    "अनुच्छेद",
    "कविता",
    "लिखो"

  ];


  if (
    writingPatterns.some(
      pattern =>
        lower.includes(pattern)
    )
  ) {

    await askAI(`

You are Novex Writing AI.

USER REQUEST:
${text}

Create polished natural writing.

Keep it concise unless the user requests long content.

`);

    return;

  }


  /* NORMAL */

  await askAI(text);

}


/* =========================================================
   CURRENT DETECTOR
========================================================= */

function needsCurrentInformation(
  text
) {

  const lower =
    text.toLowerCase();


  const currentWords = [

    "today",
    "todays",
    "today's",
    "latest",
    "current",
    "currently",
    "right now",
    "now",
    "just now",
    "recent",
    "recently",
    "live",
    "this week",
    "this month",
    "this year",
    "aaj",
    "aaj ka",
    "aaj ki",
    "abhi",
    "filhaal",
    "vartaman",
    "taaza",
    "taza",
    "ताज़ा",
    "आज",
    "अभी",
    "वर्तमान"

  ];


  if (
    currentWords.some(
      word =>
        lower.includes(word)
    )
  ) {
    return true;
  }


  const newsWords = [

    "news",
    "latest news",
    "breaking news",
    "india news",
    "world news",
    "sports news",
    "न्यूज़",
    "समाचार",
    "खबर",
    "खबरें"

  ];


  if (
    newsWords.some(
      word =>
        lower.includes(word)
    )
  ) {
    return true;
  }


  const marketWords = [

    "gold price",
    "silver price",
    "petrol price",
    "diesel price",
    "fuel price",
    "share price",
    "stock price",
    "bitcoin price",
    "crypto price",
    "dollar rate",
    "usd inr",
    "rupee rate",
    "exchange rate",
    "price today",
    "कीमत आज",
    "भाव आज",
    "आज का भाव"

  ];


  if (
    marketWords.some(
      word =>
        lower.includes(word)
    )
  ) {
    return true;
  }


  const weatherWords = [

    "weather",
    "temperature",
    "rain today",
    "forecast",
    "mausam",
    "मौसम",
    "तापमान",
    "बारिश"

  ];


  if (
    weatherWords.some(
      word =>
        lower.includes(word)
    )
  ) {
    return true;
  }


  const sportsWords = [

    "live score",
    "match today",
    "today's match",
    "ipl today",
    "cricket today",
    "football today",
    "match schedule",
    "next match",
    "next game",
    "score today",
    "लाइव स्कोर",
    "आज का मैच",
    "अगला मैच"

  ];


  if (
    sportsWords.some(
      word =>
        lower.includes(word)
    )
  ) {
    return true;
  }


  const currentRoleWords = [

    "prime minister",
    "president of india",
    "president of the united states",
    "chief minister",
    "governor of",
    "finance minister",
    "home minister",
    "defence minister",
    "defense minister",
    "current pm",
    "current president",
    "current cm",
    "who is the pm",
    "who is the prime minister",
    "who is the president",
    "who is the chief minister",
    "pm of india",
    "india's pm",
    "india pm",
    "भारत के प्रधानमंत्री",
    "भारत का प्रधानमंत्री",
    "भारत के राष्ट्रपति",
    "मुख्यमंत्री कौन",
    "प्रधानमंत्री कौन"

  ];


  if (
    currentRoleWords.some(
      word =>
        lower.includes(word)
    )
  ) {
    return true;
  }


  const scheduleWords = [

    "when is",
    "what time is",
    "what time does",
    "when will",
    "schedule",
    "opening time",
    "open today",
    "available today",
    "आज कितने बजे",
    "कब है",
    "कितने बजे"

  ];


  if (
    scheduleWords.some(
      word =>
        lower.includes(word)
    )
  ) {
    return true;
  }


  return false;

}


/* =========================================================
   AI
========================================================= */

async function askAI(
  prompt
) {

  showTyping();


  setStatus(
    "Novex is thinking..."
  );


  try {

    const response =
      await fetch(
        "/api/chat",
        {

          method:
            "POST",

          headers: {

            "Content-Type":
              "application/json",

            Authorization:
              `Bearer ${authToken}`

          },

          body:
            JSON.stringify({
              message:
                prompt
            })

        }
      );


    const data =
      await response.json();


    removeTyping();


    if (
      response.status === 401
    ) {

      forceLogout();

      return;

    }


    if (
      !response.ok ||
      !data.success
    ) {

      throw new Error(
        data.error ||
        "AI request failed"
      );

    }


    addMessage(
      "ai",
      data.answer ||
      "AI ने कोई response नहीं दिया।"
    );


    setStatus(
      "Ready to help"
    );

  }

  catch (error) {

    removeTyping();


    addMessage(
      "ai",
      "❌ " +
      error.message
    );


    setStatus(
      "Request failed"
    );

  }

}


/* =========================================================
   SEARCH
========================================================= */

async function webSearch(
  query
) {

  setStatus(
    "Searching current information..."
  );


  resetSpecialAreas();


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


  area.classList.remove(
    "hidden"
  );

  loading.classList.remove(
    "hidden"
  );

  result.innerHTML = "";


  try {

    const response =
      await fetch(
        `/api/search-ai?q=${encodeURIComponent(query)}`,
        {

          headers: {

            Authorization:
              `Bearer ${authToken}`

          }

        }
      );


    const data =
      await response.json();


    if (
      response.status === 401
    ) {

      forceLogout();

      return;

    }


    if (
      !response.ok ||
      !data.success
    ) {

      throw new Error(
        data.error ||
        "Web search failed"
      );

    }


    let html = "";


    if (data.summary) {

      html += `

        <div class="search-result">

          <strong>
            🤖 Novex Answer
          </strong>

          <p>
            ${escapeHTML(
              data.summary
            )}
          </p>

        </div>

      `;


      addMessage(
        "ai",
        data.summary
      );

    }


    if (
      data.results &&
      data.results.length
    ) {

      data.results.forEach(
        item => {

          html += `

            <div class="search-result">

              <a
                href="${escapeAttr(
                  item.url
                )}"
                target="_blank"
                rel="noopener noreferrer"
              >
                ${escapeHTML(
                  item.title
                )}
              </a>

              <span class="search-url">
                ${escapeHTML(
                  item.url
                )}
              </span>

            </div>

          `;

        }
      );

    }


    if (!html) {

      html = `

        <div class="search-result">

          Search results नहीं मिले।

        </div>

      `;

    }


    result.innerHTML =
      html;


    loading.classList.add(
      "hidden"
    );


    setStatus(
      "Current information found"
    );

  }

  catch (error) {

    loading.classList.add(
      "hidden"
    );


    result.innerHTML = `

      <div class="search-result">

        ❌
        ${escapeHTML(
          error.message
        )}

      </div>

    `;


    setStatus(
      "Search failed"
    );

  }

}


/* =========================================================
   IMAGE
========================================================= */

async function generateImage(
  prompt
) {

  resetSpecialAreas();


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


  area.classList.remove(
    "hidden"
  );

  promptText.textContent =
    prompt;

  loading.classList.remove(
    "hidden"
  );

  result.innerHTML = "";


  setStatus(
    "Creating your image..."
  );


  try {

    if (
      typeof puter ===
        "undefined" ||
      !puter.ai ||
      !puter.ai.txt2img
    ) {

      throw new Error(
        "Puter AI load नहीं हुआ। Internet check करो।"
      );

    }


    const image =
      await puter.ai.txt2img(
        prompt
      );


    let src = "";


    if (
      typeof image ===
      "string"
    ) {

      src = image;

    }

    else if (
      image?.src
    ) {

      src =
        image.src;

    }

    else if (
      image?.url
    ) {

      src =
        image.url;

    }


    if (!src) {

      throw new Error(
        "Image response नहीं मिला।"
      );

    }


    result.innerHTML = `

      <img
        src="${escapeAttr(src)}"
        alt="Novex generated image"
      >

      <a
        class="image-open"
        href="${escapeAttr(src)}"
        target="_blank"
        rel="noopener"
      >
        🖼️ Open Image
      </a>

    `;


    loading.classList.add(
      "hidden"
    );


    addMessage(
      "ai",
      "🖼️ Image successfully generated."
    );


    setStatus(
      "Image ready"
    );

  }

  catch (error) {

    loading.classList.add(
      "hidden"
    );


    result.innerHTML = `

      <div class="search-result">

        ❌
        ${escapeHTML(
          error.message
        )}

      </div>

    `;


    setStatus(
      "Image generation failed"
    );

  }

}


/* =========================================================
   WEBSITE
========================================================= */

async function generateWebsite(
  prompt
) {

  resetSpecialAreas();


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


  area.classList.remove(
    "hidden"
  );

  loading.classList.remove(
    "hidden"
  );

  result.innerHTML = "";


  setStatus(
    "Building website..."
  );


  const websitePrompt = `

You are Novex AI Website Builder.

Create a complete website for:

${prompt}

Return:
1. HTML
2. CSS
3. JavaScript

Make it responsive and functional.

Keep the response reasonably concise.

`;


  try {

    const response =
      await fetch(
        "/api/chat",
        {

          method:
            "POST",

          headers: {

            "Content-Type":
              "application/json",

            Authorization:
              `Bearer ${authToken}`

          },

          body:
            JSON.stringify({
              message:
                websitePrompt
            })

        }
      );


    const data =
      await response.json();


    if (
      response.status === 401
    ) {

      forceLogout();

      return;

    }


    if (
      !response.ok ||
      !data.success
    ) {

      throw new Error(
        data.error ||
        "Website generation failed"
      );

    }


    result.innerHTML = `

      <div class="code-box">

        <pre>
${escapeHTML(
  data.answer
)}
        </pre>

      </div>


      <button
        class="copy-btn"
        onclick='copyText(${JSON.stringify(
          data.answer
        )})'
      >
        📋 Copy Code
      </button>

    `;


    loading.classList.add(
      "hidden"
    );


    addMessage(
      "ai",
      "🌐 Website code generated successfully."
    );


    setStatus(
      "Website ready"
    );

  }

  catch (error) {

    loading.classList.add(
      "hidden"
    );


    result.innerHTML = `

      <div class="search-result">

        ❌
        ${escapeHTML(
          error.message
        )}

      </div>

    `;


    setStatus(
      "Website generation failed"
    );

  }

}


/* =========================================================
   MESSAGES
========================================================= */

function addMessage(
  role,
  text
) {

  if (!currentChat) {

    createNewLocalChat();

  }


  const welcome =
    document.getElementById(
      "welcome"
    );


  if (welcome) {

    welcome.style.display =
      "none";

  }


  currentChat.messages.push({

    role,

    text

  });


  if (
    currentChat.title ===
      "New Chat" &&
    role === "user"
  ) {

    currentChat.title =
      text.length > 40
        ? text.slice(0, 40) + "..."
        : text;

  }


  saveHistory();

  renderMessages();

  renderHistory();

}


/* =========================================================
   RENDER
========================================================= */

function renderMessages() {

  const container =
    document.getElementById(
      "messages"
    );


  if (!container) {
    return;
  }


  container.innerHTML =
    "";


  if (!currentChat) {
    return;
  }


  currentChat.messages
    .forEach(
      message => {

        const row =
          document.createElement(
            "div"
          );


        row.className =
          `message ${message.role}`;


        const avatar =
          document.createElement(
            "div"
          );


        avatar.className =
          "avatar";


        avatar.textContent =
          message.role === "user"
            ? "👤"
            : "✦";


        const body =
          document.createElement(
            "div"
          );


        body.className =
          "message-body";


        body.textContent =
          message.text;


        if (
          message.role ===
          "ai"
        ) {

          const copy =
            document.createElement(
              "button"
            );


          copy.className =
            "copy-btn";


          copy.textContent =
            "📋 Copy";


          copy.onclick =
            () =>
              copyText(
                message.text
              );


          body.appendChild(
            copy
          );

        }


        row.appendChild(
          avatar
        );


        row.appendChild(
          body
        );


        container.appendChild(
          row
        );

      }
    );


  scrollBottom();

}


/* =========================================================
   HISTORY
========================================================= */

function renderHistory() {

  const list =
    document.getElementById(
      "historyList"
    );


  if (!list) {
    return;
  }


  list.innerHTML =
    "";


  chats
    .slice(0, 30)
    .forEach(
      chat => {

        const item =
          document.createElement(
            "div"
          );


        item.className =
          "history-item";


        const title =
          document.createElement(
            "span"
          );


        title.className =
          "history-item-title";


        title.textContent =
          chat.title ||
          "New Chat";


        title.onclick =
          () => {

            currentChat =
              chat;


            resetSpecialAreas();


            renderMessages();


            const welcome =
              document.getElementById(
                "welcome"
              );


            if (welcome) {

              welcome.style.display =
                currentChat.messages.length
                  ? "none"
                  : "block";

            }


            setStatus(
              "Chat loaded"
            );

          };


        const deleteBtn =
          document.createElement(
            "button"
          );


        deleteBtn.className =
          "history-delete";


        deleteBtn.textContent =
          "🗑️";


        deleteBtn.title =
          "Delete this chat";


        deleteBtn.onclick =
          event => {

            event.preventDefault();

            event.stopPropagation();

            deleteChat(
              chat.id
            );

          };


        item.appendChild(
          title
        );


        item.appendChild(
          deleteBtn
        );


        list.appendChild(
          item
        );

      }
    );

}


/* =========================================================
   DELETE ONE CHAT
========================================================= */

function deleteChat(
  chatId
) {

  const index =
    chats.findIndex(
      chat =>
        chat.id === chatId
    );


  if (index === -1) {
    return;
  }


  const chat =
    chats[index];


  const confirmed =
    confirm(
      `"${chat.title || "New Chat"}" delete karna hai?`
    );


  if (!confirmed) {
    return;
  }


  const wasCurrent =
    currentChat &&
    currentChat.id === chatId;


  chats.splice(
    index,
    1
  );


  if (wasCurrent) {

    if (chats.length) {

      currentChat =
        chats[0];

      renderMessages();

    }

    else {

      currentChat =
        null;

      createNewLocalChat();

      renderMessages();

    }

  }


  saveHistory();

  renderHistory();

  showToast(
    "🗑️ Chat deleted"
  );

}


/* =========================================================
   CLEAR ALL
========================================================= */

function clearHistory() {

  const confirmed =
    confirm(
      "Puri chat history delete karni hai?"
    );


  if (!confirmed) {
    return;
  }


  chats = [];

  currentChat =
    null;


  createNewLocalChat();


  saveHistory();

  renderHistory();

  renderMessages();


  showToast(
    "All chats deleted"
  );

}


/* =========================================================
   TYPING
========================================================= */

function showTyping() {

  if (
    document.getElementById(
      "typing"
    )
  ) {
    return;
  }


  const row =
    document.createElement(
      "div"
    );


  row.id =
    "typing";


  row.className =
    "message ai";


  row.innerHTML = `

    <div class="avatar">
      ✦
    </div>

    <div class="message-body">
      Novex is thinking...
    </div>

  `;


  document.getElementById(
    "messages"
  ).appendChild(
    row
  );


  scrollBottom();

}


function removeTyping() {

  const typing =
    document.getElementById(
      "typing"
    );


  if (typing) {
    typing.remove();
  }

}


/* =========================================================
   SIDEBAR
========================================================= */

function toggleSidebar() {

  document
    .getElementById(
      "sidebar"
    )
    .classList.toggle(
      "open"
    );

}


/* =========================================================
   SPECIAL
========================================================= */

function resetSpecialAreas() {

  [
    "imageArea",
    "websiteArea",
    "searchArea"
  ]
  .forEach(
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
   VOICE
========================================================= */

function startVoiceInput() {

  const Recognition =
    window.SpeechRecognition ||
    window.webkitSpeechRecognition;


  if (!Recognition) {

    showToast(
      "Voice input browser me supported nahi hai."
    );

    return;

  }


  const recognition =
    new Recognition();


  recognition.lang =
    "hi-IN";


  recognition.continuous =
    false;


  recognition.interimResults =
    true;


  recognition.onstart =
    () => {

      showToast(
        "🎤 Sun raha hoon..."
      );

    };


  recognition.onresult =
    event => {

      let text = "";


      for (
        let i = event.resultIndex;
        i < event.results.length;
        i++
      ) {

        text +=
          event.results[i][0]
            .transcript;

      }


      const input =
        document.getElementById(
          "userInput"
        );


      input.value =
        text;


      autoResize(input);

    };


  recognition.onerror =
    () => {

      showToast(
        "Voice input error"
      );

    };


  recognition.start();

}


/* =========================================================
   KEYBOARD
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
   RESIZE
========================================================= */

function autoResize(
  element
) {

  element.style.height =
    "auto";


  element.style.height =
    Math.min(
      element.scrollHeight,
      140
    ) + "px";

}


/* =========================================================
   THEME
========================================================= */

function setTheme(
  theme
) {

  document.body
    .classList.remove(
      "theme-white"
    );


  if (
    theme === "white"
  ) {

    document.body
      .classList.add(
        "theme-white"
      );

  }


  localStorage.setItem(
    "novex_theme",
    theme
  );


  document
    .getElementById(
      "themeMenu"
    )
    .classList.remove(
      "show"
    );


  showToast(
    theme === "white"
      ? "⚪ White theme"
      : "⚫ Black theme"
  );

}


function loadTheme() {

  const theme =
    localStorage.getItem(
      "novex_theme"
    ) || "black";


  if (
    theme === "white"
  ) {

    document.body
      .classList.add(
        "theme-white"
      );

  }

}


function toggleThemeMenu() {

  document
    .getElementById(
      "themeMenu"
    )
    .classList.toggle(
      "show"
    );

}


/* =========================================================
   STATUS
========================================================= */

function setStatus(
  text
) {

  const element =
    document.getElementById(
      "statusText"
    );


  if (element) {

    element.textContent =
      text;

  }

}


/* =========================================================
   COPY
========================================================= */

async function copyText(
  text
) {

  try {

    await navigator.clipboard
      .writeText(
        text
      );


    showToast(
      "📋 Copied"
    );

  }

  catch {

    showToast(
      "Copy failed"
    );

  }

}


/* =========================================================
   FORCE LOGOUT
========================================================= */

function forceLogout() {

  localStorage.removeItem(
    "novex_auth_token"
  );


  authToken = "";

  currentUser =
    null;

  chats = [];

  currentChat =
    null;


  showAuth();

  showLogin();


  showToast(
    "Session expired. Login again."
  );

}


/* =========================================================
   TOAST
========================================================= */

function showToast(
  message
) {

  const toast =
    document.getElementById(
      "toast"
    );


  toast.textContent =
    message;


  toast.classList.add(
    "show"
  );


  setTimeout(
    () => {

      toast.classList.remove(
        "show"
      );

    },
    2200
  );

}


/* =========================================================
   ESCAPE HTML
========================================================= */

function escapeHTML(
  text
) {

  return String(text)

    .replace(
      /&/g,
      "&amp;"
    )

    .replace(
      /</g,
      "&lt;"
    )

    .replace(
      />/g,
      "&gt;"
    )

    .replace(
      /"/g,
      "&quot;"
    )

    .replace(
      /'/g,
      "&#039;"
    );

}


/* =========================================================
   ESCAPE ATTRIBUTE
========================================================= */

function escapeAttr(
  text
) {

  return String(text)

    .replace(
      /&/g,
      "&amp;"
    )

    .replace(
      /"/g,
      "&quot;"
    )

    .replace(
      /</g,
      "&lt;"
    )

    .replace(
      />/g,
      "&gt;"
    );

}


/* =========================================================
   SCROLL
========================================================= */

function scrollBottom() {

  const content =
    document.querySelector(
      ".content"
    );


  if (!content) {
    return;
  }


  setTimeout(
    () => {

      content.scrollTop =
        content.scrollHeight;

    },
    40
  );

}