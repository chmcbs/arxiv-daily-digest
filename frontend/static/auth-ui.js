function setPageStatus(statusEl, message, isError) {
  statusEl.textContent = message || "";
  if (!message) {
    statusEl.style.removeProperty("color");
    return;
  }
  statusEl.style.color = isError ? "#b91c1c" : "#6b7280";
}

async function checkAuthenticatedSession({ sessionLabelEl, authGateEl, appEl }) {
  const session = await apiRequest("/auth/session", "GET");
  if (!session.authenticated) {
    sessionLabelEl.textContent = "Not signed in";
    authGateEl.classList.remove("hidden");
    appEl.classList.add("hidden");
    return false;
  }
  sessionLabelEl.textContent = session.email;
  authGateEl.classList.add("hidden");
  appEl.classList.remove("hidden");
  return true;
}

function bindMagicLinkForm({ formEl, statusEl, linkWrapEl, linkEl, nextPath = "" }) {
  formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.getElementById("auth-email").value.trim();
    statusEl.textContent = "Sending magic link...";
    linkWrapEl.classList.add("hidden");
    try {
      const payload = await apiRequest("/auth/magic-link/request", "POST", { email });
      statusEl.textContent = "Check your inbox for the confirmation link.";
      if (payload.magic_link) {
        linkEl.href = nextPath
          ? `${payload.magic_link}&next=${encodeURIComponent(nextPath)}`
          : payload.magic_link;
        linkWrapEl.classList.remove("hidden");
      }
    } catch (error) {
      statusEl.textContent = String(error.message || error);
    }
  });
}
