const COPY = {
  unsubscribed: {
    title: "Successfully unsubscribed.",
    message: "You will no longer receive daily digest emails.",
  },
  invalid: {
    title: "Invalid link.",
    message: "Sign in using the button below to update your email settings.",
  },
};

function initEmailPreferencesPage() {
  const params = new URLSearchParams(window.location.search);
  const status = params.get("status") || "invalid";
  const copy = COPY[status] || COPY.invalid;

  document.getElementById("email-preferences-title").textContent = copy.title;
  document.getElementById("email-preferences-message").textContent = copy.message;
}

initEmailPreferencesPage();
