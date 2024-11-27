# -*- coding: utf-8 -*-
"""DominosFinal.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1z5RzAsZUI26V8XBrO5SjY41Ber4kigKk
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from prophet import Prophet
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_percentage_error
from sklearn.model_selection import train_test_split
import seaborn as sns

# Load datasets
ingredients_file_path = 'Pizza_ingredients.xlsx'
sales_file_path = 'Pizza_Sale.xlsx'

# Load data
ingredients_df = pd.ExcelFile(ingredients_file_path).parse('Pizza_ingredients')
sales_df = pd.ExcelFile(sales_file_path).parse('pizza_sales')

sales_df.head()

# Data Preprocessing
sales_df['order_date'] = pd.to_datetime(sales_df['order_date'])
sales_df['year'] = sales_df['order_date'].dt.year
sales_df['month'] = sales_df['order_date'].dt.month
sales_df['day_of_week'] = sales_df['order_date'].dt.dayofweek
sales_df['is_weekend'] = sales_df['day_of_week'].apply(lambda x: 1 if x >= 5 else 0)

# Handling Missing Values
ingredients_df.fillna(method='ffill', inplace=True)
sales_df.fillna(method='ffill', inplace=True)

# Standardizing invalid ingredient values
ingredients_df['pizza_ingredients'] = ingredients_df['pizza_ingredients'].str.strip().str.replace(r'\s+', ' ', regex=True)

# Drop rows with invalid dates
sales_df = sales_df.dropna(subset=['order_date'])

# Aggregate daily sales
daily_sales = sales_df.groupby('order_date').agg({'quantity': 'sum'}).reset_index()
daily_sales.rename(columns={'quantity': 'total_sales'}, inplace=True)

# Handle missing dates by filling missing days with 0 sales
full_date_range = pd.date_range(start=daily_sales['order_date'].min(), end=daily_sales['order_date'].max())
daily_sales = daily_sales.set_index('order_date').reindex(full_date_range).fillna(0).reset_index()
daily_sales.rename(columns={'index': 'order_date'}, inplace=True)

# Feature Engineering
daily_sales['moving_avg_7'] = daily_sales['total_sales'].rolling(window=7).mean()
daily_sales['lag_1'] = daily_sales['total_sales'].shift(1)
daily_sales['lag_7'] = daily_sales['total_sales'].shift(7)
daily_sales.fillna(0, inplace=True)

# Create a new column for day names
sales_df['Day'] = sales_df['order_date'].dt.day_name()

# Aggregating sales by date and pizza category
sales_agg = sales_df.groupby(['order_date', 'pizza_category'])['quantity'].sum().reset_index()

# Exploratory Data Analysis (EDA)
# Plotting sales trends
plt.figure(figsize=(10, 6))
sns.lineplot(data=sales_agg, x='order_date', y='quantity', hue='pizza_category')
plt.title('Sales Trends by Pizza Type')
plt.xlabel('Date')
plt.ylabel('Quantity Sold')
plt.xticks(rotation=45)
plt.show()

# Adding a revenue column
sales_df['Revenue'] = sales_df['quantity'] * sales_df['total_price']

# Calculating total revenue by category
revenue_by_category = sales_df.groupby('pizza_category')['Revenue'].sum().reset_index().sort_values(by='Revenue', ascending=False)

# Plotting the revenue by category
plt.figure(figsize=(8, 5))
sns.barplot(data=revenue_by_category, x='pizza_category', y='Revenue')
plt.title('Revenue by Pizza Category')
plt.xlabel('Pizza Category')
plt.ylabel('Total Revenue')
plt.show()

# Aggregating revenue by month
monthly_revenue = sales_df.groupby('month')['Revenue'].sum().reset_index()

# Plotting monthly revenue trends
plt.figure(figsize=(10, 5))
sns.lineplot(data=monthly_revenue, x='month', y='Revenue')
plt.title('Monthly Revenue Trends')
plt.xlabel('Month')
plt.ylabel('Total Revenue')
plt.xticks(rotation=45)
plt.show()

# Merge the datasets
sales_ingredients = sales_df.merge(ingredients_df, on='pizza_name_id', how='inner', suffixes=('_sales', '_ingredients'))

# Group by ingredients and sum the quantity
ingredient_usage = sales_ingredients.groupby('pizza_ingredients_ingredients')['Items_Qty_In_Grams'].sum().reset_index()

# Sorting the results
ingredient_usage = ingredient_usage.sort_values(by='Items_Qty_In_Grams', ascending=False)

# Plotting ingredient usage
plt.figure(figsize=(12, 6))
sns.barplot(data=ingredient_usage.head(10), x='pizza_ingredients_ingredients', y='Items_Qty_In_Grams')
plt.title('Top 10 Most Used Ingredients')
plt.xlabel('Ingredient')
plt.ylabel('Total Quantity Needed')
plt.xticks(rotation=45)
plt.show()

"""**From above analysis the insights I get are as follows**- **1**. The Classic pizza category exhibits the highest variability in daily sales, with frequent spikes in demand. **2**. This highlights that the Classic pizzas are both popular and profitable. **3**. Planning for ingredient purchases should heavily consider Chicken, Red Onions, and Capocollo, as they are crucial for production. **4**. The cyclical nature of revenue suggests potential seasonality in customer behavior."""

# Parse Dates Explicitly
sales_df['order_date'] = pd.to_datetime(sales_df['order_date'], format='%d-%m-%Y', errors='coerce')

# Aggregate sales by date and pizza_name_id
daily_sales = sales_df.groupby(['order_date', 'pizza_name_id']).agg({'quantity': 'sum'}).reset_index()

# Handling Outliers in Quantity
Q1 = daily_sales['quantity'].quantile(0.25)
Q3 = daily_sales['quantity'].quantile(0.75)
IQR = Q3 - Q1
lower_bound = Q1 - 1.5 * IQR
upper_bound = Q3 + 1.5 * IQR
daily_sales = daily_sales[(daily_sales['quantity'] >= lower_bound) & (daily_sales['quantity'] <= upper_bound)]

# Aggregate sales by week
daily_sales['week'] = daily_sales['order_date'].dt.to_period('W').apply(lambda r: r.start_time)
weekly_sales = daily_sales.groupby(['week', 'pizza_name_id']).agg({'quantity': 'sum'}).reset_index()

# Define forecasting functions
def train_prophet(train_data, test_data):
    prophet_data = train_data.rename(columns={'week': 'ds', 'quantity': 'y'})
    prophet_model = Prophet()
    prophet_model.fit(prophet_data)
    future_dates = pd.DataFrame({'ds': test_data['week']})
    forecast = prophet_model.predict(future_dates)
    predictions = forecast['yhat']
    mape = mean_absolute_percentage_error(test_data['quantity'], predictions)
    return mape, predictions

def train_arima(train_data, test_data):
    arima_model = ARIMA(train_data['quantity'], order=(5, 1, 0))
    arima_result = arima_model.fit()
    predictions = arima_result.forecast(steps=len(test_data))
    mape = mean_absolute_percentage_error(test_data['quantity'], predictions)
    return mape, predictions

def train_sarima(train_data, test_data):
    sarima_model = SARIMAX(train_data['quantity'], order=(1, 1, 1), seasonal_order=(1, 1, 1, 52))
    sarima_result = sarima_model.fit(disp=False)
    predictions = sarima_result.forecast(steps=len(test_data))
    mape = mean_absolute_percentage_error(test_data['quantity'], predictions)
    return mape, predictions

def train_xgboost(train_data, test_data):
    train_data['week_of_year'] = train_data['week'].dt.isocalendar().week
    train_data['year'] = train_data['week'].dt.year
    test_data['week_of_year'] = test_data['week'].dt.isocalendar().week
    test_data['year'] = test_data['week'].dt.year
    x_train = train_data[['week_of_year', 'year']]
    y_train = train_data['quantity']
    x_test = test_data[['week_of_year', 'year']]
    xgb_model = XGBRegressor(objective='reg:squarederror', n_estimators=100, max_depth=5, learning_rate=0.1)
    xgb_model.fit(x_train, y_train)
    predictions = xgb_model.predict(x_test)
    mape = mean_absolute_percentage_error(test_data['quantity'], predictions)
    return mape, predictions

# Split data into train and test sets
train_data = weekly_sales[weekly_sales['week'] < '2015-12-01']
test_data = weekly_sales[weekly_sales['week'] >= '2015-12-01']

# Train and Evaluate Models
prophet_mape, _ = train_prophet(train_data, test_data)
arima_mape, _ = train_arima(train_data, test_data)
sarima_mape, _ = train_sarima(train_data, test_data)
xgb_mape, _ = train_xgboost(train_data, test_data)

# Compare MAPEs
model_performance = {
    'Prophet': prophet_mape,
    'ARIMA': arima_mape,
    'SARIMA': sarima_mape,
    'XGBoost': xgb_mape
}

best_model_name = min(model_performance, key=model_performance.get)
print(f"\nModel Performance (MAPE): {model_performance}")
print(f"Best Model: {best_model_name}")

# Use the Best Model for Weekly Predictions
if best_model_name == 'Prophet':
    _, predictions = train_prophet(train_data, test_data)
elif best_model_name == 'ARIMA':
    _, predictions = train_arima(train_data, test_data)
elif best_model_name == 'SARIMA':
    _, predictions = train_sarima(train_data, test_data)
elif best_model_name == 'XGBoost':
    _, predictions = train_xgboost(train_data, test_data)

# Generate Weekly Forecast
test_data['predicted_quantity'] = predictions

# Merge with ingredients for weekly ingredient requirements
forecast_with_ingredients = test_data.merge(ingredients_df, on='pizza_name_id', how='left')
forecast_with_ingredients['Total_Ingredient_Grams'] = (
    forecast_with_ingredients['predicted_quantity'] * forecast_with_ingredients['Items_Qty_In_Grams']
)

# Final Output
result = forecast_with_ingredients[['week', 'pizza_name_id', 'predicted_quantity', 'pizza_ingredients', 'Total_Ingredient_Grams']]

# Display Results
print("\nFinal Weekly Forecast with Ingredients Requirements:")
print(result)

# Save the result in an Excel file
result.to_excel('Total_Weekly_Ingredients_Quantity.xlsx', index=False)