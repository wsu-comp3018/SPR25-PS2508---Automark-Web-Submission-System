// -------------------------------
    // Client-side validation helpers
    // -------------------------------
    function validateEmail(email) {
        const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return regex.test(email);
    }

    function validateUsername(username) {
        const regex = /^[a-zA-Z0-9_]{3,20}$/;
        return regex.test(username);
    }

    function showError(elementId, message) {
        const errorElement = document.getElementById(elementId);
        errorElement.textContent = message;
        errorElement.style.display = 'block';
    }

    function hideError(elementId) {
        const errorElement = document.getElementById(elementId);
        errorElement.style.display = 'none';
    }

    function showSuccess(elementId, message) {
        const successElement = document.getElementById(elementId);
        successElement.textContent = message;
        successElement.style.display = 'block';
    }

    function hideSuccess(elementId) {
        const successElement = document.getElementById(elementId);
        successElement.style.display = 'none';
    }

    function showLoading(elementId) {
        document.getElementById(elementId).style.display = 'flex';
    }

    function hideLoading(elementId) {
        document.getElementById(elementId).style.display = 'none';
    }

    // -------------------------------
    // API calls to Flask backend
    // -------------------------------
    async function apiRegister(userData) {
        const res = await fetch("/api/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(userData),
        });
        return res.json();
    }

    async function apiLogin(credentials) {
        const res = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(credentials),
        });
        return res.json();
    }

    // -------------------------------
    // Sign Up Form Handler
    // -------------------------------
    document.getElementById("signupForm").addEventListener("submit", async function(e) {
        e.preventDefault();
        hideSuccess("signup-success");
        ["username-error", "email-error", "password-error", "confirm-password-error", "signup-error"].forEach(hideError);

        const formData = {
            username: document.getElementById("signup-username").value.trim(),
            email: document.getElementById("signup-email").value.trim(),
            password: document.getElementById("signup-password").value,
            confirmPassword: document.getElementById("confirm-password").value,
            role: document.getElementById("signup-role").value,
            first_name: document.getElementById("first-name").value.trim(),
            last_name: document.getElementById("last-name").value.trim(),
        };

        // Basic client-side checks
        let hasErrors = false;
        if (!validateUsername(formData.username)) {
            showError("username-error", "Username must be 3-20 characters, letters, numbers, and underscores only");
            hasErrors = true;
        }
        if (!validateEmail(formData.email)) {
            showError("email-error", "Please enter a valid email address");
            hasErrors = true;
        }
        if (formData.password.length < 6) {
            showError("password-error", "Password must be at least 6 characters long");
            hasErrors = true;
        }
        if (formData.password !== formData.confirmPassword) {
            showError("confirm-password-error", "Passwords do not match");
            hasErrors = true;
        }
        if (hasErrors) return;

        showLoading("signup-loading");

        try {
            const result = await apiRegister(formData);
            hideLoading("signup-loading");
            if (result.success) {
                showSuccess("signup-success", result.message);
                this.reset();
                setTimeout(() => {
                    document.getElementById("password-strength-bar").style.width = "0%";
                    hideSuccess("signup-success");
                }, 2000);
            } else {
                showError("signup-error", result.message);
            }
        } catch (err) {
            hideLoading("signup-loading");
            showError("signup-error", "Server error. Try again.");
        }
    });

    // -------------------------------
    // Sign In Form Handler
    // -------------------------------
    document.getElementById("signinForm").addEventListener("submit", async function(e) {
        e.preventDefault();
        ["signin-username-error", "signin-password-error", "signin-error"].forEach(hideError);
        hideSuccess("signin-success");

        const credentials = {
            identifier: document.getElementById("signin-username").value.trim(),
            password: document.getElementById("signin-password").value,
        };

        if (!credentials.identifier || !credentials.password) {
            showError("signin-error", "Please enter both username/email and password");
            return;
        }

        showLoading("signin-loading");

        try {
            const result = await apiLogin(credentials);
            hideLoading("signin-loading");

            if (result.success) {
                showSuccess("signin-success", result.message);

                // Save session locally
                localStorage.setItem("automark_user", JSON.stringify(result));

                // Redirect after delay
                setTimeout(() => {
                    if (result.role === "student") {
                        window.location.href = "studentdash.html";
                    } else {
                        window.location.href = "lecture-dashboard.html";
                    }
                }, 2000);
            } else {
                showError("signin-error", result.message);
            }
        } catch (err) {
            hideLoading("signin-loading");
            showError("signin-error", "Server error. Try again.");
        }
    });

    // -------------------------------
    // Forgot password (demo only)
    // -------------------------------
    function showForgotPassword() {
        const email = prompt("Please enter your email address:");
        if (email && validateEmail(email)) {
            alert("Password reset instructions sent to " + email);
        } else if (email) {
            alert("Invalid email address");
        }
    }

    window.showForgotPassword = showForgotPassword;