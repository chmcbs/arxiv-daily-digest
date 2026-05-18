const authGate = document.getElementById("auth-gate");
const prefsApp = document.getElementById("prefs-app");
const authStatus = document.getElementById("auth-status");
const authLinkWrap = document.getElementById("auth-link-wrap");
const authLink = document.getElementById("auth-link");
const sessionLabel = document.getElementById("session-label");
const prefsStatus = document.getElementById("prefs-status");
const profilesGrid = document.getElementById("profiles-grid");
const addProfileBtn = document.getElementById("add-profile-btn");
const cardTemplate = document.getElementById("profile-card-template");

let categories = [];
let profiles = [];

function setStatus(message, isError) {
  prefsStatus.textContent = message;
  prefsStatus.style.color = isError ? "#b91c1c" : "#6b7280";
}

async function checkSession() {
  const session = await apiRequest("/auth/session", "GET");
  if (!session.authenticated) {
    sessionLabel.textContent = "Not signed in";
    authGate.classList.remove("hidden");
    prefsApp.classList.add("hidden");
    return false;
  }
  sessionLabel.textContent = session.email;
  authGate.classList.add("hidden");
  prefsApp.classList.remove("hidden");
  return true;
}

async function loadCategories() {
  const payload = await apiRequest("/categories", "GET");
  categories = payload.categories || [];
}

async function loadProfiles() {
  const payload = await apiRequest("/profiles", "GET");
  profiles = payload.profiles || [];
  renderProfiles();
}

function renderProfiles() {
  profilesGrid.innerHTML = "";
  if (!profiles.length) {
    profilesGrid.innerHTML = "<p class='muted'>No profiles yet. Add your first profile.</p>";
    return;
  }

  profiles.forEach((profile) => {
    const node = cardTemplate.content.firstElementChild.cloneNode(true);
    node.querySelector(".profile-title").textContent = `Profile ${profile.profile_slot}`;
    const nameInput = node.querySelector(".profile-name-input");
    const categorySelect = node.querySelector(".category-select");
    const interestText = node.querySelector(".interest-text");
    const digestCheckbox = node.querySelector(".digest-checkbox");
    const keywordInput = node.querySelector(".keyword-input");
    const keywordList = node.querySelector(".keyword-list");
    const saveBtn = node.querySelector(".save-btn");
    const deleteBtn = node.querySelector(".delete-btn");
    const addKeywordBtn = node.querySelector(".keyword-add-btn");

    nameInput.value = profile.profile_name;
    interestText.value = profile.interest_sentence;
    digestCheckbox.checked = profile.digest_enabled;

    categories.forEach((category) => {
      const option = document.createElement("option");
      option.value = category;
      option.textContent = category;
      if (category === profile.category) {
        option.selected = true;
      }
      categorySelect.appendChild(option);
    });

    function drawKeywords(values) {
      keywordList.innerHTML = "";
      values.forEach((value) => {
        const chip = document.createElement("span");
        chip.className = "keyword-chip";
        chip.textContent = value;
        const removeBtn = document.createElement("button");
        removeBtn.className = "chip-btn";
        removeBtn.textContent = "x";
        removeBtn.type = "button";
        removeBtn.addEventListener("click", async () => {
          try {
            const payload = await apiRequest(`/profiles/${profile.profile_id}/keywords`, "DELETE", { keyword: value });
            profile.keywords = payload.keywords;
            drawKeywords(profile.keywords);
            setStatus("Keyword removed.", false);
          } catch (error) {
            setStatus(String(error.message || error), true);
          }
        });
        chip.appendChild(removeBtn);
        keywordList.appendChild(chip);
      });
    }

    drawKeywords(profile.keywords || []);

    addKeywordBtn.addEventListener("click", async () => {
      const keyword = keywordInput.value.trim();
      if (!keyword) {
        return;
      }
      try {
        const payload = await apiRequest(`/profiles/${profile.profile_id}/keywords`, "POST", { keyword });
        profile.keywords = payload.keywords;
        keywordInput.value = "";
        drawKeywords(profile.keywords);
        setStatus("Keyword added.", false);
      } catch (error) {
        setStatus(String(error.message || error), true);
      }
    });

    saveBtn.addEventListener("click", async () => {
      try {
        const updatePayload = await apiRequest(`/profiles/${profile.profile_id}`, "PUT", {
          profile_name: nameInput.value,
          category: categorySelect.value,
          digest_enabled: digestCheckbox.checked,
        });
        profile.profile_name = updatePayload.profile.profile_name;
        profile.category = updatePayload.profile.category;
        profile.digest_enabled = updatePayload.profile.digest_enabled;
        const selectedIds = profiles.filter((item) => item.digest_enabled).map((item) => item.profile_id);
        await apiRequest("/profiles/digest-selection", "PUT", { profile_ids: selectedIds });
        setStatus("Profile saved.", false);
      } catch (error) {
        setStatus(String(error.message || error), true);
      }
    });

    deleteBtn.addEventListener("click", async () => {
      try {
        await apiRequest(`/profiles/${profile.profile_id}`, "DELETE", {});
        profiles = profiles.filter((item) => item.profile_id !== profile.profile_id);
        const selectedIds = profiles.filter((item) => item.digest_enabled).map((item) => item.profile_id);
        await apiRequest("/profiles/digest-selection", "PUT", { profile_ids: selectedIds });
        renderProfiles();
        setStatus("Profile deleted.", false);
      } catch (error) {
        setStatus(String(error.message || error), true);
      }
    });

    profilesGrid.appendChild(node);
  });
}

document.getElementById("auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = document.getElementById("auth-email").value.trim();
  authStatus.textContent = "Sending magic link...";
  authLinkWrap.classList.add("hidden");
  try {
    const payload = await apiRequest("/auth/magic-link/request", "POST", { email });
    authStatus.textContent = "Check your inbox for the confirmation link.";
    if (payload.magic_link) {
      authLink.href = payload.magic_link;
      authLinkWrap.classList.remove("hidden");
    }
  } catch (error) {
    authStatus.textContent = String(error.message || error);
  }
});

addProfileBtn.addEventListener("click", async () => {
  if (profiles.length >= 3) {
    setStatus("Profile limit reached (3).", true);
    return;
  }
  try {
    const slot = profiles.length + 1;
    const payload = await apiRequest("/profiles", "POST", {
      profile_name: `Profile ${slot}`,
      category: categories[0] || "cs.AI",
      interest_sentence: "Describe your research interests.",
    });
    profiles.push(payload.profile);
    renderProfiles();
    setStatus("Profile created.", false);
  } catch (error) {
    setStatus(String(error.message || error), true);
  }
});

async function init() {
  try {
    const authenticated = await checkSession();
    if (!authenticated) {
      return;
    }
    await loadCategories();
    await loadProfiles();
    setStatus("Ready.", false);
  } catch (error) {
    setStatus(String(error.message || error), true);
  }
}

init();
