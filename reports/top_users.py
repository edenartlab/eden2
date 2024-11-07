from datetime import datetime, timedelta

import sys
sys.path.append(".")

from mongo import get_collection

users = get_collection("users", env="PROD")
tasks = get_collection("tasks2", env="PROD")

# Calculate date one month ago
one_month_ago = datetime.now() - timedelta(days=30)

# Use aggregation to count tasks per user
task_counts = tasks.aggregate([
    # Match tasks from last month
    {"$match": {"createdAt": {"$gte": one_month_ago}}},
    
    # Group by user and count tasks
    {"$group": {
        "_id": "$user",
        "task_count": {"$sum": 1}
    }},
    
    # Sort by task count descending
    {"$sort": {"task_count": -1}}
])

# Print header
print(f"{'Rank':<6}{'Username':<20}{'Email':<30}{'Tasks':<8}")
print("-" * 64)  # Separator line

# Print aligned data
for i, task_stat in enumerate(task_counts):
    user = users.find_one({"_id": task_stat["_id"]})
    if user:
        print(f"{i+1:<6}{user.get('username', 'Unknown'):<20}{user.get('email', 'Unknown'):<30}{task_stat['task_count']:<8}")
    
# Save results to CSV
import csv
from pathlib import Path

# Create reports directory if it doesn't exist
Path("reports/data").mkdir(parents=True, exist_ok=True)

# Generate filename with current timestamp
filename = f"reports/data/top_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

with open(filename, 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    # Write header
    writer.writerow(['Rank', 'Username', 'Email', 'Tasks'])
    
    # Reset the aggregation cursor since we already consumed it
    task_counts = tasks.aggregate([
        {"$match": {"createdAt": {"$gte": one_month_ago}}},
        {"$group": {"_id": "$user", "task_count": {"$sum": 1}}},
        {"$sort": {"task_count": -1}}
    ])
    
    # Write data rows
    for i, task_stat in enumerate(task_counts):
        user = users.find_one({"_id": task_stat["_id"]})
        if user:
            writer.writerow([
                i+1,
                user.get('username', 'Unknown'),
                user.get('email', 'Unknown'),
                task_stat['task_count']
            ])

print(f"\nReport saved to: {filename}")
    