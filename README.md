# Ayush's Daybook

The Daybook runs as a local web app and saves editable data in SQLite on this computer.

## Run it

1. Open Terminal.
2. Run:

   ```sh
   cd "/Users/ashleykafle/Documents/MyDaybooks"
   python3 server.py
   ```

3. Open <http://127.0.0.1:4173>.

Keep the Terminal window open while using the app. Closing it stops the local server; it does not delete the database. Start the server again with the same command to continue. The server listens only on this computer, not on the public network.

## Data and backups

- The SQLite database is `data/daybook.sqlite3`.
- The existing Claude export is kept as archived records in that database, separate from the editable daybook state.
- Edits to priorities, check-ins, tasks, Journal, and Looking back are saved to SQLite automatically. The browser keeps a local copy as a fallback.
- Swipe left or right on the timeline block or selected-day label to move between yesterday, today, and tomorrow. On a trackpad, use a horizontal swipe over either area. Each date has its own priorities, check-ins, energy, note, and schedule shape, and navigation stays within those three days.
- Use **SQLite backup** to download a complete copy of the database.
- Use **JSON backup** for a portable export of the archived sections and current editable state.
- The **Fun** tab can refresh upcoming Cincinnati and Northern Kentucky events from Visit Cincy and Cincinnati Zoo public calendars. The first check starts when the local server starts, then checks weekly while it is running; failed sources are retried daily. Use **Refresh suggestions** to check immediately. Each suggestion links to its source, and source failures are shown without deleting that source's saved results.

Keep backups somewhere safe. The database is local to this computer and is not synced to another device or cloud service automatically.

Automatic event checks only run while the local server is running. They pause when the computer is asleep or the server is closed, and resume the next time the server starts. Event listings are provided by third-party sites and may change or become unavailable; confirm dates, availability, and details with the organizer before making plans.
