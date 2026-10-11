import sqlite3
from datetime import datetime

DATABASE_NAME = 'my_database.db'

def create_database():
    """Create a new SQLite database if it doesn't exist."""
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    # Create the table if it doesn't exist
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            application_name TEXT NOT NULL,
            window_title TEXT NOT NULL,
            duration_seconds REAL NOT NULL)
        """
    )

    connection.commit()
    connection.close()

def log_activity(application_name: str, window_title: str, duration_seconds: float):
    """Log an activity to the database."""
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    timestamp_now = datetime.now().isoformat()  # Get the current timestamp in ISO format

    cursor.execute(
        """
        INSERT INTO activities (timestamp, application_name, window_title, duration_seconds)
        VALUES (?, ?, ?, ?)
        """,
        (timestamp_now, application_name, window_title, round(duration_seconds, 2))
    )

    connection.commit()
    connection.close()

def get_summary():
    """Retrieve a summary of activities from the database."""
    connection = sqlite3.connect(DATABASE_NAME)
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT application_name, window_title, SUM(duration_seconds) as total_duration
        FROM activities
        GROUP BY application_name, window_title
        ORDER BY total_duration DESC
        """
    )

    summary = cursor.fetchall()
    connection.close()
    return summary

if __name__ == "__main__":
    create_database()
    # Example usage: log an activity
    print("Database created successfully.")