# Convert date to datetime format and sort by date
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(by='date')

# Separate sales and production orders
sales_orders = df[df['transaction_type'] == 'sales_order'].copy()
production_orders = df[df['transaction_type'] == 'production_order'].copy()

# Check weekend days
from datetime import datetime

# Function to label weekend days
def is_weekend(date):
    return date.weekday() >= 5  # Saturday = 5, Sunday = 6

# Add weekday info to sales and production
sales_orders['weekday'] = sales_orders['date'].apply(lambda x: x.strftime('%A'))
production_orders['weekday'] = production_orders['date'].apply(lambda x: x.strftime('%A'))

# Summarize the data to understand the full range
summary = {
    "Total Sales Orders": sales_orders['quantity'].sum(),
    "Total Production Orders": production_orders['quantity'].sum(),
    "Sales Order Range": (sales_orders['date'].min(), sales_orders['date'].max()),
    "Production Order Range": (production_orders['date'].min(), production_orders['date'].max()),
    "Sales Orders on Weekend": sales_orders[sales_orders['date'].apply(is_weekend)].shape[0],
    "Production Orders on Weekend": production_orders[production_orders['date'].apply(is_weekend)].shape[0],
}

summary


from datetime import timedelta
import numpy as np

# Parameters
scrap_rate = 0.05
factory_capacity = 100
initial_stock = 2

# Prepare sales orders
sales_orders = sales_orders.sort_values(by="date")

# Calculate required production (with scrap and stock)
inventory = initial_stock
optimized_production_orders = []

# Iterate through each sales order and calculate required production
for idx, row in sales_orders.iterrows():
    sales_date = row['date']
    required_qty = abs(row['quantity'])

    # Check available stock
    if inventory >= required_qty:
        inventory -= required_qty
        continue

    # Calculate net required
    net_required = required_qty - inventory

    # Calculate production quantity needed considering scrap
    production_qty = int(np.ceil(net_required / (1 - scrap_rate)))

    # Schedule production to complete at least 1 day before sales date
    prod_date = sales_date - timedelta(days=1)

    # Split over days if needed (considering no weekends)
    while production_qty > 0:
        while prod_date.weekday() >= 5:  # Skip weekends
            prod_date -= timedelta(days=1)

        day_qty = min(factory_capacity, production_qty)
        optimized_production_orders.append({
            "date": prod_date,
            "product": "Product A",
            "type": "🛠️ Production Order",
            "quantity": day_qty
        })

        # Update inventory: only 95% is usable
        inventory += int(day_qty * (1 - scrap_rate))
        production_qty -= day_qty
        prod_date -= timedelta(days=1)

# Combine with original sales orders
formatted_sales = sales_orders.rename(columns={
    'date': 'date',
    'product': 'product',
    'quantity': 'quantity'
})
formatted_sales['type'] = '💰 Sales Order'

# Final combined result
final_schedule = pd.concat([
    pd.DataFrame(optimized_production_orders),
    formatted_sales[['date', 'product', 'type', 'quantity']]
])

# Sort chronologically
final_schedule = final_schedule.sort_values(by='date').reset_index(drop=True)

# Format for output
final_schedule['date'] = final_schedule['date'].dt.strftime('%Y-%m-%d')
final_schedule
