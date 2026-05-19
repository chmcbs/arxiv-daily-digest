const form = document.getElementById("signup-form");
const statusEl = document.getElementById("signup-status");
const linkWrap = document.getElementById("signup-link-wrap");
const linkEl = document.getElementById("signup-link");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = document.getElementById("email").value.trim();
  statusEl.textContent = "Sending magic link...";
  linkWrap.classList.add("hidden");
  try {
    const payload = await apiRequest("/auth/magic-link/request", "POST", { email });
    if (payload.magic_link) {
      statusEl.textContent = "Dev mode: use the link below to sign in.";
      linkEl.href = payload.magic_link;
      linkWrap.classList.remove("hidden");
    } else {
      statusEl.textContent = "Check your inbox for the confirmation link.";
    }
  } catch (error) {
    statusEl.textContent = String(error.message || error);
  }
});
