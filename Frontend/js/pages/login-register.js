import { register, login } from "../services/authService.js";

const $ = (id) => document.getElementById(id);
const toast = (msg) => alert(msg); // swap for nicer UI if you want

// SIGN UP
const signupForm = $("signupForm");
if (signupForm) {
  signupForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      username: $("signup-username").value.trim(),
      email: $("signup-email").value.trim(),
      password: $("signup-password").value,
      role: $("signup-role").value,
      first_name: $("first-name").value.trim(),
      last_name: $("last-name").value.trim()
    };
    try {
      await register(payload);
      toast("Registration successful! Please sign in.");
    } catch (err) {
      if (err.status === 409) toast("Username or email already exists.");
      else toast(`Sign-up failed: ${err.message}`);
    }
  });
}

// SIGN IN
const signinForm = $("signinForm");
if (signinForm) {
  signinForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = $("signin-username").value.trim();
    const password = $("signin-password").value;
    const remember_me = $("remember-me")?.checked || false;
    try {
      const data = await login({ username, password, remember_me });
      const role = data?.user?.role || $("signin-role")?.value || "student";
      location.href = role === "lecturer" ? "lecturer-dashboard.html" : "studentdash.html";
    } catch (err) {
      toast(`Sign-in failed: ${err.message}`);
    }
  });
}
