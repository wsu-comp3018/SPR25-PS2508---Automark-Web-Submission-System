// js/pages/login-register.js
// Works with login&register.html + FastAPI backend

// login-register.js loaded

// -------------------------------
// Small helpers
// -------------------------------
const $ = (id) => document.getElementById(id);

function showError(id, msg) {
  const el = $(id);
  if (!el) return;
  el.textContent = msg || "";
  el.style.display = "block";
}
function hideError(id) {
  const el = $(id);
  if (!el) return;
  el.style.display = "none";
}
function showSuccess(id, msg) {
  const el = $(id);
  if (!el) return;
  el.textContent = msg || "";
  el.style.display = "block";
}
function hideSuccess(id) {
  const el = $(id);
  if (!el) return;
  el.style.display = "none";
}
function showLoading(id) {
  const el = $(id);
  if (!el) return;
  el.style.display = "flex";
}
function hideLoading(id) {
  const el = $(id);
  if (!el) return;
  el.style.display = "none";
}

// -------------------------------
// Validation helpers
// -------------------------------
function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}
function validateUsername(username) {
  return /^[a-zA-Z0-9_]{3,20}$/.test(username);
}
function updateStrengthBar() {
  const pw = $("signup-password")?.value || "";
  const bar = $("password-strength-bar");
  if (!bar) return;

  let strength = 0;
  if (pw.length >= 8) strength += 25;
  if (/[a-z]/.test(pw)) strength += 25;
  if (/[A-Z]/.test(pw)) strength += 25;
  if (/[0-9]/.test(pw)) strength += 12.5;
  if (/[^a-zA-Z0-9]/.test(pw)) strength += 12.5;

  bar.style.width = `${strength}%`;
  bar.className = "password-strength-bar";
  if (strength < 50) bar.classList.add("strength-weak");
  else if (strength < 75) bar.classList.add("strength-medium");
  else bar.classList.add("strength-strong");
}

// -------------------------------
// UI toggles
// -------------------------------
function initializeUI() {
  console.log("🚀 Initializing UI...");
  const container = $("container");
  const signUpBtn = $("signUp");
  const signInBtn = $("signIn");

  console.log("Elements found:", { container, signUpBtn, signInBtn });

  if (signUpBtn) {
    signUpBtn.addEventListener("click", (e) => {
      e.preventDefault();
      console.log("Sign Up button clicked - adding right-panel-active class");
      container?.classList.add("right-panel-active");
    });
    console.log("✅ Sign Up button event listener added");
  } else {
    console.log("❌ Sign Up button not found!");
  }
  if (signInBtn) {
    signInBtn.addEventListener("click", (e) => {
      e.preventDefault();
      console.log("Sign In button clicked - removing right-panel-active class");
      container?.classList.remove("right-panel-active");
    });
    console.log("✅ Sign In button event listener added");
  } else {
    console.log("❌ Sign In button not found!");
  }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeUI);
} else {
  initializeUI();
}

window.toggleForms = function toggleForms() {
  const container = $("container");
  container?.classList.toggle("right-panel-active");
};

window.showForgotPassword = function showForgotPassword() {
  const email = prompt("Please enter your email address:");
  if (email && validateEmail(email)) {
    alert("Password reset instructions sent to " + email);
  } else if (email) {
    alert("Invalid email address");
  }
};

// -------------------------------
// Backend API calls (FastAPI)
// -------------------------------
const API_BASE = "https://54-197-160-146.nip.io/api/v1/auth";

async function apiRegister(payload) {
  const res = await fetch(`${API_BASE}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail || "Registration failed");
  }
  return data;
}

async function apiLogin(credentials) {
  const res = await fetch(`${API_BASE}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(credentials),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail || "Invalid credentials");
  }
  return data;
}

// -------------------------------
// Form wiring
// -------------------------------
$("signup-password")?.addEventListener("input", updateStrengthBar);

$("signup-username")?.addEventListener("blur", () => {
  const v = $("signup-username").value.trim();
  if (v && !validateUsername(v)) showError("username-error", "Username must be 3-20 characters (letters, numbers, underscore).");
  else hideError("username-error");
});
$("signup-email")?.addEventListener("blur", () => {
  const v = $("signup-email").value.trim();
  if (v && !validateEmail(v)) showError("email-error", "Please enter a valid email address");
  else hideError("email-error");
});
$("confirm-password")?.addEventListener("input", () => {
  const p = $("signup-password")?.value || "";
  const c = $("confirm-password")?.value || "";
  if (c && p !== c) showError("confirm-password-error", "Passwords do not match");
  else hideError("confirm-password-error");
});

// Submit: Sign Up
$("signupForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  ["username-error", "email-error", "password-error", "confirm-password-error", "signup-error"].forEach(hideError);
  hideSuccess("signup-success");

  const payload = {
    username: $("signup-username").value.trim(),
    email: $("signup-email").value.trim(),
    password: $("signup-password").value,
    role: $("signup-role").value,
    first_name: $("first-name").value.trim(),
    last_name: $("last-name").value.trim(),
  };

  let hasErrors = false;
  if (!validateUsername(payload.username)) {
    showError("username-error", "Invalid username format");
    hasErrors = true;
  }
  if (!validateEmail(payload.email)) {
    showError("email-error", "Invalid email");
    hasErrors = true;
  }
  if ((payload.password || "").length < 6) {
    showError("password-error", "Password must be at least 6 characters");
    hasErrors = true;
  }
  if ($("signup-password").value !== $("confirm-password").value) {
    showError("confirm-password-error", "Passwords do not match");
    hasErrors = true;
  }
  if (hasErrors) return;

  showLoading("signup-loading");
  try {
    await apiRegister(payload);
    hideLoading("signup-loading");
    showSuccess("signup-success", "Account created successfully!");
    $("signupForm").reset();
    $("password-strength-bar").style.width = "0%";

    setTimeout(() => {
      hideSuccess("signup-success");
      const container = $("container");
      container?.classList.remove("right-panel-active");
    }, 1200);
  } catch (err) {
    hideLoading("signup-loading");
    showError("signup-error", err.message);
  }
});

// Submit: Sign In
$("signinForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  ["signin-error"].forEach(hideError);
  hideSuccess("signin-success");

  const username = $("signin-username").value.trim(); // can be username OR email
  const password = $("signin-password").value;
  const remember_me = $("remember-me")?.checked || false;

  if (!username || !password) {
    showError("signin-error", "Please enter both username/email and password");
    return;
  }

  showLoading("signin-loading");
  try {
    const result = await apiLogin({ username, password, remember_me });
    hideLoading("signin-loading");
    showSuccess("signin-success", "Login successful");

    localStorage.setItem("automark_token", result.token);
    localStorage.setItem("automark_user", JSON.stringify(result.user));

    showDashboardPreview(result.user);
  } catch (err) {
    hideLoading("signin-loading");
    showError("signin-error", err.message);
  }
});

// -------------------------------
// Dashboard preview
// -------------------------------
function showDashboardPreview(user) {
  const modal = $("dashboard-preview");
  if (modal) modal.style.display = "flex";
  setTimeout(() => redirectToDashboard(user), 1500);
}
function redirectToDashboard(user) {
  const role = (user?.role || "student").toLowerCase();
  const map = {
    student: "studentdash.html",
    lecturer: "lecturer-dashboard.html",
  };
  window.location.href = map[role] || map.student;
}

// -------------------------------
// UX niceties
// -------------------------------
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    const container = $("container");
    const active = container?.classList.contains("right-panel-active")
      ? $("signupForm")
      : $("signinForm");
    active?.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
  }
});
