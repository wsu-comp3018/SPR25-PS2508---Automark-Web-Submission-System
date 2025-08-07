const express = require("express");
const bodyParser = require("body-parser");
const { Client } = require("ssh2");
const cors = require("cors");


const app = express();
app.use(cors());
app.use(bodyParser.json());

function sshAuthenticate(username, password) {
    return new Promise((resolve, reject) => {
        const conn = new Client();
        conn.on("ready", () => {
            conn.end();
            resolve(true);
        })
        .on("error", (err) => {
            reject(err);
        })
        .connect({
            host: "YOUR_SSH_SERVER_IP",
            port: 22,
            username,
            password
        });
    });
}

app.post("/api/login", async (req, res) => {
    const { username, password } = req.body;
    try {
        await sshAuthenticate(username, password);
        res.json({ success: true, message: "SSH Login successful" });
    } catch {
        res.status(401).json({ success: false, message: "SSH Authentication failed" });
    }
});

app.listen(3000, () => console.log("Server running on port 3000"));
