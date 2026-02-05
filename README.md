# ARIN IPv4 Waiting List Monitor

This tool monitors your position on the **ARIN IPv4 Waiting List** and sends an email update on every check.

Because ARIN renders the waiting list **client-side with JavaScript**, this script uses **Playwright (headless Chromium)** to load the page exactly as a browser would, then extracts your position reliably.

---

## Features

- ✅ Scrapes the **real ARIN waiting list table** (JS-rendered)
- ✅ Matches your entry by **exact “Date and Time Added to Waiting List”**
- ✅ Sends updates to **multiple email recipients**
- ✅ Supports **SMTP (STARTTLS)** and **SMTPS (implicit TLS / 465)**
- ✅ Runs **on demand** (`--once`) or **every 12 hours** (`--watch`)
- ✅ Verbose logging — you can see exactly what it’s doing
- ✅ Gracefully degrades (prints output if email fails)

---

## Requirements

- Linux (Debian/Ubuntu recommended)
- Python **3.9+**
- Outbound HTTPS access
- Outbound SMTP access (or local mail relay)

---

## Installation

### 1️⃣ Clone the repository
```bash
git clone https://github.com/YOURUSERNAME/arin-waitlist-monitor.git
cd arin-waitlist-monitor
