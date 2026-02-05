# ARIN IPv4 Waiting List Monitor

This project monitors your position on the ARIN IPv4 Waiting List and sends an email update every time it runs.

ARIN renders the IPv4 waiting list table using client-side JavaScript, which means traditional scraping tools such as curl, requests, or BeautifulSoup will not work. This script uses Playwright with headless Chromium to load the page exactly like a real browser and extract the rendered table reliably.

This tool is designed to be run manually or automatically on a schedule and is suitable for long-term unattended use on a server.

---

## Overview

When the script runs, it loads the ARIN IPv4 waiting list page in a headless browser, reads the fully rendered table, locates your entry by matching the exact “Date and Time Added to Waiting List”, and sends an email showing your current position. The previous position is stored locally so each run can report progress over time.

The script supports running on demand or on a fixed schedule such as every twelve hours.

---

## System Requirements

A Linux system is recommended, specifically Debian or Ubuntu. Python version 3.9 or newer is required. The system must have outbound HTTPS access to reach arin.net. Email delivery requires access to an SMTP server using either implicit TLS on port 465 or STARTTLS on port 587.

---

## Installation

System packages must be installed first to support Python virtual environments and Playwright.

On Debian or Ubuntu systems, install the required packages using apt. After cloning the repository, create a Python virtual environment and activate it. Install Playwright and then install the Chromium browser that Playwright requires.

All Playwright browser dependencies are installed automatically by the Playwright installer.

---

## Configuration

Configuration is handled using environment variables loaded from a local file. This file must not be committed to GitHub.

The most important value is the ARIN_TARGET_DATE. This must exactly match the “Date and Time Added to Waiting List” value shown on the ARIN website for your request.

SMTP configuration values define how email notifications are sent. The script supports both SMTPS on port 465 and SMTP with STARTTLS on port 587. Multiple email recipients are supported and can be provided as a comma, semicolon, or space separated list.

The environment file is loaded before running the script so that credentials and configuration are not hard-coded.

---

## Running the Script Manually

The script can be run manually at any time. When run manually, it loads the waiting list, finds your entry, and sends an email showing your current position and the previous recorded position.

Manual execution is useful for testing configuration, validating email delivery, or performing an immediate status check.

---

## Running Automatically Every Twelve Hours

The script is designed to be run on a schedule. The most common approach is to use cron, which allows the script to execute every twelve hours with no user interaction.

For server environments, a systemd service and timer can be used instead. This provides better logging, persistence across reboots, and cleaner long-term operation.

Both approaches run the script in single-run mode and rely on the scheduler to control the interval.

---

## Email Notification Format

Each execution sends an email in the following format:

Your current ARIN IPv4 waiting list position is:
XXX/XXX.

Your last position was:
XXX/XXX.

You joined the waitlist on:
<Date used for matching>

Max Prefix: /XX | Min Prefix: /XX

Time Checked:
MM/DD/YYYY HH:MMPM CST

The email subject line includes the current position so changes can be identified at a glance.

---

## Logging and State Tracking

Each run records the last known position in a local state file. This file is updated automatically and should not be committed to version control.

When the script runs via cron or systemd, standard output can be redirected to a log file for troubleshooting and auditing.

---

## Troubleshooting

If the script reports that no table rows were found, Chromium may not be installed correctly. Reinstalling the Playwright browser dependencies typically resolves this issue.

If email delivery fails, outbound SMTP connectivity should be tested from the server. Many hosting providers restrict outbound SMTP traffic, in which case a relay or email API service may be required.

---

## Security Notes

Environment files containing SMTP credentials must never be committed to GitHub. SMTP passwords should be rotated if they are ever exposed. The local state file should also be excluded from version control.

---

## Disclaimer

This project is not affiliated with or endorsed by ARIN. ARIN may change page structure, policies, or data formats at any time, which could require updates to this script.
