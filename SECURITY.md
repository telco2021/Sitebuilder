# What was left behind

The uploaded ASP.NET tree was treated as untrusted. It was read, not executed, and none of its binaries, database files, or scripts were copied into this project.

## Not a classic web shell

The VB, ASPX, JavaScript, and SQL text did not contain a hidden command shell, an encoded payload, or a second-stage downloader. The `lubri` and `pearl` script notes differ from the main validation script only in alert text and a couple of button toggles.

That does not make the tree safe. Several behaviors would become a back door if they were rebuilt, and the binaries were not disassembled far enough to call them clean. They were excluded instead of reused.

## Excluded on purpose

- Compiled libraries, including the payment component that posts full card data, writes a log at the root of the C: drive, and touches the registry. The chart and zip libraries were not reused either.
- The compiled hotel assembly and its debug symbols, which point at an old IIS site.
- The SQL Server data and log files. They contain guest records, plaintext staff passwords, and card data. Nothing in them was imported. The sample hotel uses invented room inventory. Its name and street are the public hotel from the old desk. The phone and email are fictional.
- The web configuration file. It held a database administrator password and an internal server address.
- Client scripts that write a remote response straight into the page, plus the obfuscated calendar and the date popup that evaluates a string.
- The license check that phones a vendor host on startup.
- The order-export path that downloads a URL and treats the response as a filesystem location, including the commented debug mail that sent paths and order XML to a hard-coded mailbox.
- Hotel staff self-registration. Anyone who could open that page could create an administrator and receive the password by email. Staff accounts here are created by an owner.
- String-built SQL, plaintext passwords, and pages that were allowed to inject script into the public site.
- Live card charging. A booking keeps the brand, the last four digits, the expiry, and a reference. The full number and security code are checked and discarded. Sequences that look like card numbers are removed from comments.

## Modules brought over from the newest CMS source on hand

The 9 September 2008 CMS source is the latest CMS file in the archive folder. News, banners, the calendar, services, the gallery, courses, RV coaches, coupons, tell-a-friend, and the message queue are rebuilt from that behavior.

Left out of those modules on purpose:

- Phone-network delivery. A queued message stays in the database.
- The banner sign-in page. Staff who already run the site manage banners.
- Card numbers on coupon sales and on coach offers. A coupon is text. An offer is an amount and a note.
- Plaintext course passwords and passwords built from a record number.
- Loading a vehicle XML file from the upload folder.
- The calendar iframe. Events are a list of dates.
- Merchant accounts that can publish their own coupons before a publisher approves them.

## What this edition does instead

The application makes no outbound HTTP calls. Sessions are signed, forms require a per-session token, passwords are hashed, and published HTML is reduced to a small set of tags. Generated sites are new Python files plus the published content. They do not wrap the old source.

Re-check this file and `tests/test_quarantine.py` before adding any code that came from the old tree.

## This project file

The Visual Studio 2003 project file names the public gallery, the shop, accounts, banners, the calendar, forms, and a hotel path. It also names appointments, a carrier shipping page, and a payment page. Those three were file names only. Their source was not in this upload, so they were not reconstructed.

The uploaded page source that did arrive is the image and video gallery, plus the application startup that copies feature switches into the session. Feature switches stay on the site settings page. The gallery compares a password hash, pages images and videos, and advances a slide with a refresh. It does not build SQL from the request, does not keep the album password, and does not embed an ActiveX, QuickTime, or Flash player. Locked albums are left out of a generated site.

The web configuration in the upload held a database login, an empty administrator password, a license value, and internal addresses. None of those values were copied. The compiled libraries in the same upload were not linked or shipped.
