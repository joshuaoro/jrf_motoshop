# JRF Motorcycle Shop System - Complete Project Documentation

## 0. Defense-Oriented System Walkthrough (What / Why / How)

This section is written specifically to help you defend the project in front of panelists.
For every major part of the system we answer three questions:

- **What** is this part?
- **Why** did we design it this way?
- **How** does it work technically?

After reading this section, you can use the rest of the document as reference.

### 0.1 Big Picture: What is the JRF System?

- **What**: A full **Motorcycle Parts Shop Management System**:
  - Inventory, suppliers, customers, sales (POS), expenses, maintenance, reports, backups, notifications and audit logging.
- **Why**:
  - Replace manual notebooks / Excel with a reliable, centralized system.
  - Reduce stock-outs and over-stocking.
  - Give the owner clear visibility on sales, expenses and profit.
  - Track who did what in the system for accountability.
- **How**:
  - Built as a **Flask web app** with:
    - **MySQL** + SQLAlchemy for data.
    - **Flask-Login** for authentication.
    - **Role-Based Access Control (RBAC)** for permissions.
    - **HTML + Tailwind CSS + JS** for UI.
    - Clearly separated **routes**, **models**, and **templates**.

### 0.2 High-Level Architecture (How everything is organized)

- **What**:
  - A classic **3‑layer web architecture**:
    - Presentation layer (templates + JS)
    - Application layer (Flask routes + business logic in `app.py`)
    - Data layer (MySQL database with models and relationships)
- **Why**:
  - Separation of concerns makes the system easier to maintain and extend.
  - Each layer can evolve independently (e.g., change UI without changing DB).
- **How**:
  - **Requests** go: Browser → Flask route → ORM (models) → MySQL.
  - **Responses** go back: MySQL → ORM → Flask → HTML/JSON → Browser.
  - Real‑time dashboard polling uses `/api/...` endpoints returning JSON.

### 0.3 Core Data Model (The "nouns" of the system)

The main entities (tables / models) are:

- **User / Staff** (`User` model, `staff` table)
- **Part** (products / inventory items)
- **Supplier**
- **Customer**
- **`Sale` + `SaleDetail`** (transactions and line items)
- **`PurchaseOrder` + `PurchaseOrderItem`**
- **Expense**
- **MaintenanceLog**
- **Settings**
- **Notification**
- **`BackupLog`, `AuditLog`, `SystemLog`**

For each entity:

- **What**: Represents a real‑world concept (e.g., a part on the shelf).
- **Why**: Needed to support business operations (selling, stocking, tracking).
- **How**: Implemented as a SQLAlchemy model with:
  - `__tablename__` mapping to a MySQL table.
  - Columns (`db.Column`) mapping to fields.
  - Relationships (`db.relationship`) capturing links between tables.

(See the later sections “Database Models Explained” and “Database Objects Implementation”
for full field‑by‑field technical detail.)

### 0.4 Authentication & Roles (Who can do what)

- **What**:
  - Users log in with email + password.
  - Roles: `admin`, `manager`, `staff`.
- **Why**:
  - Protect sensitive features (e.g., staff management, reports).
  - Ensure only authorized people can change critical data.
- **How**:
  - `User` model extends `UserMixin` and stores `password_hash` and `role`.
  - Passwords are hashed using `generate_password_hash` and checked with `check_password_hash`.
  - `Flask-Login` manages sessions (`login_user`, `logout_user`, `current_user`).
  - Helper methods like `is_admin()`, `can_manage_inventory()` encapsulate permissions.
  - Decorators `@admin_required`, `@manager_required`, `@role_required(...)` wrap routes:
    - If permission fails, the route flashes an error and redirects to `dashboard`.

### 0.5 Inventory Module (Parts, stock levels and suppliers)

- **What**:
  - Screens to **view**, **search**, and **inspect** all parts.
  - Shows stock levels, suppliers and performance metrics per part.
- **Why**:
  - The core of the business is selling the right parts.
  - Owner needs to see which parts are low, which are fast‑moving, which suppliers supply them.
- **How**:
  - `inventory.html` lists parts using data from `/inventory` route.
  - `Part` model stores name, brand, type, price, `stock_quantity`, and description.
  - Many‑to‑many link with `Supplier` via `supplier_part` table.
  - A part detail modal calls `/api/parts/<id>/sales-metrics` to show:
    - Total quantity sold.
    - Total revenue.
    - Last sale date.
  - Low‑stock thresholds from `Settings` and the notification helpers generate alerts.

### 0.6 Sales / POS Module

- **What**:
  - Point‑of‑sale page to add parts to a cart, choose customer and payment method, and complete a sale.
- **Why**:
  - Replace manual writing of receipts with a system that automatically:
    - Deducts stock.
    - Logs revenue.
    - Links the sale to staff and customer.
- **How**:
  - Frontend (`sales.html`) manages cart in JavaScript and then posts to `/api/sales`.
  - Backend:
    - Creates a `Sale` record (total amount, payment method, date, customer, staff).
    - Creates `SaleDetail` records for each line item.
    - Deducts stock from `Part.stock_quantity`.
    - Checks for low stock and creates **critical low stock notifications** for managers.
    - Checks if sale is **high value** (threshold from `Settings`):
      - Sends notifications to managers and admins.
    - Every 10 sales, sends a **sales milestone** notification.
    - Creates an audit log entry with details of the sale.

### 0.7 Customers & Suppliers

- **Customers**
  - **What**: Records who buys from the shop.
  - **Why**: For customer‑based analytics (who are top buyers, repeat customers).
  - **How**:
    - `Customer` model linked to `Sale` via `customer_id`.
    - `customers.html` allows add/edit of customers through `/api/customers` endpoints.

- **Suppliers**
  - **What**: Companies or individuals who supply parts.
  - **Why**: Needed for reordering, tracking which supplier is responsible for which parts.
  - **How**:
    - `Supplier` model + `supplier_part` association.
    - `suppliers.html` shows each supplier and `parts_count` (how many parts they supply).
    - The inventory modal shows related suppliers for a part.

### 0.8 Expenses, Maintenance & Purchase Orders

- **Expenses**
  - **What**: Non‑stock costs (rent, utilities, misc. expenses).
  - **Why**: To calculate **net profit** (sales − expenses).
  - **How**:
    - `Expense` model stores category, amount, date, notes.
    - Routes and APIs allow recording and listing expenses.
    - Reports aggregate expenses per period and category.

- **MaintenanceLog**
  - **What**: Tracks maintenance done on equipment or specific parts.
  - **Why**:
    - Shows true cost of keeping certain equipment running.
    - Helps decide whether to repair or replace.
  - **How**:
    - `MaintenanceLog` links to `Part` (which item is maintained).
    - High‑cost maintenance triggers notifications for managers.

- **Purchase Orders**
  - **What**: Requests sent to suppliers to replenish stock.
  - **Why**: Formalize the reordering process and trace what was ordered, when, and from whom.
  - **How**:
    - `PurchaseOrder` and `PurchaseOrderItem` models.
    - Inventory page can trigger creation of purchase orders for low‑stock parts.

### 0.9 Notifications System

- **What**:
  - Centralized in‑app notifications for important events:
    - Critical low stock, high‑value sales, sales milestones, high‑cost maintenance, completed backups, etc.
- **Why**:
  - Keep managers informed **without spamming** them for every small action.
  - Support better, quicker decisions (e.g., reorder before stock runs out).
- **How**:
  - `Notification` model stores:
    - `user_id`, `title`, `message`, `type` (`info`, `warning`, `error`, `success`),
    - `category`, `action_url`, `action_text`, `is_read`.
  - Helper functions:
    - `create_notification(user_id, ...)`
    - `create_notification_for_role(role, ...)`
    - `create_notification_for_all(...)`
  - Business logic in routes (e.g., `/api/sales`, maintenance, backup endpoint) call these helpers.
  - Frontend:
    - Header bell icon fetches recent notifications and unread count.
    - A portal renders the dropdown **on top of all content** using high `z-index`.

### 0.10 Audit Logs, Backups and System Logs

- **AuditLog**
  - **What**: Records important user actions (create/update/delete) on key entities.
  - **Why**: Accountability and traceability (who changed what, and when).
  - **How**:
    - `log_audit(action, entity, entity_id, old_data, new_data, user_id)` helper.
    - Called from routes after important write operations (e.g., sales, settings).

- **BackupLog**
  - **What**: Records database backup operations.
  - **Why**: Proof that backups are happening; helps in disaster recovery planning.
  - **How**:
    - `/api/backup` endpoint triggers backup logic and creates a `BackupLog` row.
    - `settings.html` shows last backup time.

- **SystemLog**
  - **What**: Technical log of system‑level events or errors.
  - **Why**: Helps developers and admins diagnose problems.

### 0.11 Dashboard & Reports

- **Dashboard**
  - **What**: High‑level overview page.
  - **Why**: Allows the owner/manager to see the health of the business at a glance.
  - **How**:
    - `dashboard()` route at `/` and `/dashboard`.
    - Uses helper `get_realtime_stats()` to compute:
      - Total parts, low stock count, today’s sales count, today’s revenue, etc.
    - Frontend cards visualize these values.

- **Reports**
  - **What**: Detailed analytics for sales and expenses.
  - **Why**: Support strategic decisions: what to stock, which customers to focus on, which products are top sellers.
  - **How**:
    - `reports.html` + corresponding routes aggregate:
      - Sales by date, by product, by customer.
      - Expenses by category.
    - Uses chart libraries on the frontend for visualization.

### 0.12 Real-Time Behaviour

- **What**:
  - Some pages auto‑refresh data every 30 seconds.
- **Why**:
  - Dashboard and other key stats should stay up‑to‑date without manual refresh.
- **How**:
  - `static/js/realtime.js` runs an interval that calls APIs like:
    - `/api/todays-sales`, `/api/sales-data`, `/api/recent-activities`.
  - The responses update numbers and charts in the DOM.

### 0.13 Settings Module

- **What**:
  - Central configuration for the system: general, inventory, sales, notifications, backup, security.
- **Why**:
  - Make the system flexible without changing code (e.g., thresholds, auto‑backup frequency, high‑value sale threshold).
- **How**:
  - `Settings` model stores `category`, `setting_key`, `setting_value` as strings.
  - `init_default_settings()` seeds sensible defaults if they don’t exist.
  - `/settings` route loads all settings and passes them to `settings.html`.
  - `/api/settings` (GET/POST/PUT) allows the frontend to read and update settings via AJAX.

### 0.14 Frontend Design Choices

- **What**:
  - Consistent modern UI using `base_new.html` as the shell (sidebar + header).
- **Why**:
  - Panelists and users should immediately understand navigation.
  - Clean, professional look supports the credibility of the system.
- **How**:
  - Tailwind utility classes for spacing, typography and layout.
  - Custom CSS variables (`--primary`, `--secondary`, etc.) for theme colors.
  - Gradients removed and replaced with solid colors to simplify and standardize the design.
  - Reusable components: sidebar, header with notifications and profile dropdown, cards, badges, buttons.

### 0.15 How to Explain the System to Panelists (Cheat Sheet)

When asked **“What does your system do?”**:
- It is an **end‑to‑end management system** for a motorcycle parts shop:
  - It tracks **inventory**, **suppliers**, **customers**, **sales**, **expenses**, **maintenance**, and **backups**.
  - It provides **real-time dashboard**, **notifications**, and **detailed reports**.

When asked **“Why did you design it this way?”**:
- We used **MySQL + Flask + SQLAlchemy** for:
  - Reliability and ACID transactions.
  - Cleaner object‑oriented code (models instead of raw SQL).
  - Easier to maintain and extend.
- We implemented **RBAC** and **audit logging** for:
  - Security, accountability, and future audit / compliance requirements.
- We separated frontend templates from backend logic:
  - Designers can work on HTML/CSS while developers focus on Python.

When asked **“How does feature X work?”**:
- Answer in this pattern:
  - **What**: Describe the feature in one sentence.
  - **Why**: Explain the business problem it solves.
  - **How**: Mention the key models, routes, and templates involved.

After this section, the rest of this document goes into deeper, line‑by‑line
technical details that you can refer to when preparing specific answers.

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Project Architecture](#project-architecture)
3. [Initial Setup and Dependencies](#initial-setup-and-dependencies)
4. [Detailed Import Analysis](#detailed-import-analysis)
5. [Database Models Explained](#database-models-explained)
6. [MySQL Connection Process](#mysql-connection-process)
7. [Database Objects Implementation](#database-objects-implementation)
8. [Role-Based Access Control (RBAC)](#role-based-access-control-rbac)
9. [API Endpoints and Routes](#api-endpoints-and-routes)
10. [Security Implementation](#security-implementation)
11. [How Everything Works Together](#how-everything-works-together)

---

## 1. Project Overview

### What is This Project?

The **JRF Motorcycle Shop System** is a comprehensive web-based inventory and sales management system designed specifically for motorcycle parts and accessories businesses. It's built as a **Flask web application** that provides:

- **Inventory Management**: Track motorcycle parts, stock levels, suppliers
- **Point-of-Sale (POS) System**: Process sales transactions
- **User Management**: Staff accounts with role-based access
- **Reporting**: Sales analytics and inventory reports
- **Real-time Updates**: Dashboard with live statistics

### Technology Stack

- **Backend Framework**: Flask (Python web framework)
- **Database**: MySQL (required - no fallback)
- **ORM**: SQLAlchemy (database abstraction layer)
- **Authentication**: Flask-Login (session management)
- **Authorization**: Role-Based Access Control (RBAC)
- **Frontend**: HTML, Tailwind CSS, JavaScript
- **Database Driver**: PyMySQL (MySQL connector for Python)

---

## 2. Project Architecture

### File Structure

```
jrf_system/
├── app.py                      # Main Flask application (780 lines)
├── init_db.py                  # Database initialization script
├── requirements.txt            # Python package dependencies
├── database_objects.sql       # SQL definitions for stored procedures, functions, triggers
├── setup_database_objects.py   # Script to create database objects
├── .env                        # Environment variables (database credentials)
├── templates/                  # HTML templates
│   ├── base.html              # Base template with navigation
│   ├── base_new.html          # Updated base template
│   ├── dashboard.html         # Main dashboard
│   ├── inventory.html         # Inventory management page
│   ├── sales.html             # Point-of-sale system
│   ├── login.html             # Login page
│   ├── suppliers.html         # Supplier management
│   ├── staff.html             # Staff management
│   ├── reports.html           # Reports and analytics
│   └── settings.html          # System settings
├── static/                     # Static assets
│   └── css/
│       └── style.css          # Custom CSS styles
└── .env                        # Environment variables (MySQL credentials - REQUIRED)
```

### Application Flow

```
User Request → Flask App → Authentication Check → Route Handler → 
Database Query (MySQL) → Process Data → Return Response (HTML/JSON)
```

---

## 3. Initial Setup and Dependencies

### Step-by-Step Project Creation

#### Step 1: Project Initialization

The project started as a Flask application. Here's how it was set up:

1. **Created the main application file** (`app.py`)
   - This is the entry point of the application
   - Contains all routes, models, and business logic

2. **Set up virtual environment** (recommended)
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Created requirements.txt** with all necessary packages

#### Step 2: Installing Dependencies

The `requirements.txt` file contains all Python packages needed:

```txt
Flask==2.3.3
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.2
Flask-WTF==1.2.1
python-dotenv==1.0.0
Werkzeug==2.3.7
email-validator==2.1.0
Flask-Migrate==4.0.5
pymysql==1.1.0
```

**Installation command:**
```bash
pip install -r requirements.txt
```

---

## 4. Detailed Import Analysis

Let's break down **every single import** in `app.py` and explain why it's needed:

### Line 1: Flask Core Imports

```python
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
```

**Why each import is needed:**

1. **`Flask`**: 
   - The main Flask class that creates the web application instance
   - Used as: `app = Flask(__name__)`
   - This creates the WSGI application that handles HTTP requests

2. **`render_template`**:
   - Renders HTML templates with dynamic data
   - Used in routes like: `return render_template('dashboard.html', data=data)`
   - Combines HTML templates with Python variables

3. **`request`**:
   - Accesses incoming HTTP request data
   - Used to get form data: `request.form.get('email')`
   - Used to get query parameters: `request.args.get('threshold')`
   - Used to get JSON data: `request.get_json()`

4. **`redirect`**:
   - Redirects user to a different URL
   - Used after login: `return redirect(url_for('index'))`
   - Used for navigation between pages

5. **`url_for`**:
   - Generates URLs for routes by their function names
   - Used as: `url_for('index')` → generates `/dashboard`
   - Makes URLs maintainable (change route path without breaking links)

6. **`flash`**:
   - Stores messages to display to users (success/error messages)
   - Used as: `flash('Invalid email or password', 'error')`
   - Messages are shown on the next page load

7. **`jsonify`**:
   - Converts Python dictionaries/lists to JSON responses
   - Used for API endpoints: `return jsonify({'success': True})`
   - Required for AJAX/fetch requests from frontend

### Line 2: Database ORM

```python
from flask_sqlalchemy import SQLAlchemy
```

**Why it's needed:**
- **SQLAlchemy** is an Object-Relational Mapping (ORM) library
- Allows us to work with databases using Python objects instead of SQL
- Instead of writing: `SELECT * FROM parts WHERE id = 1`
- We write: `Part.query.get(1)`
- Provides database abstraction, making it easy to switch databases
- Used as: `db = SQLAlchemy(app)` to create database instance

### Line 3: Authentication

```python
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
```

**Why each import is needed:**

1. **`LoginManager`**:
   - Manages user sessions and authentication
   - Used as: `login_manager = LoginManager()`
   - Handles login/logout functionality

2. **`UserMixin`**:
   - Provides default implementations for user authentication methods
   - Our `User` class inherits from it: `class User(UserMixin, db.Model)`
   - Provides methods like `is_authenticated()`, `is_active()`, etc.

3. **`login_user`**:
   - Logs a user into the session
   - Used in login route: `login_user(user)`
   - Creates a session cookie that identifies the logged-in user

4. **`login_required`**:
   - Decorator that protects routes from unauthorized access
   - Used as: `@login_required` above route functions
   - Redirects to login page if user not authenticated

5. **`logout_user`**:
   - Logs out the current user
   - Used in logout route: `logout_user()`
   - Clears the session

6. **`current_user`**:
   - Access the currently logged-in user object
   - Used as: `current_user.id` to get user ID
   - Available in all routes when user is logged in

### Line 4: Password Security

```python
from werkzeug.security import generate_password_hash, check_password_hash
```

**Why it's needed:**
- **Security**: Never store passwords in plain text!
- **`generate_password_hash`**: 
  - Converts plain password to secure hash
  - Used when creating/updating passwords: `generate_password_hash('admin123')`
  - Creates a one-way hash that cannot be reversed
  - Uses PBKDF2 algorithm with salt

- **`check_password_hash`**:
  - Verifies if a password matches the stored hash
  - Used in login: `check_password(password)`
  - Compares entered password with stored hash

**Example:**
```python
# When creating user
password_hash = generate_password_hash('admin123')
# Stores: 'pbkdf2:sha256:260000$...' (long secure string)

# When logging in
if check_password_hash(stored_hash, 'admin123'):
    # Password matches!
```

### Line 5: Date/Time Handling

```python
from datetime import datetime, timedelta
```

**Why it's needed:**
- **`datetime`**: 
  - Handles dates and times
  - Used for: `datetime.utcnow()` to get current time
  - Used in models: `sale_date = db.Column(db.DateTime, default=datetime.utcnow)`
  - Used for filtering: `Sale.query.filter(Sale.sale_date >= week_ago)`

- **`timedelta`**:
  - Represents time differences
  - Used as: `datetime.utcnow() - timedelta(days=30)` to get date 30 days ago
  - Used for date range queries

### Line 6: Operating System Interface

```python
import os
```

**Why it's needed:**
- Accesses environment variables
- Used as: `os.getenv('SECRET_KEY')` to get configuration from `.env` file
- Used for: `os.getenv('DATABASE_URL')` to get database connection string
- Keeps sensitive data (passwords, keys) out of code

### Line 7: Environment Variables

```python
from dotenv import load_dotenv
```

**Why it's needed:**
- Loads variables from `.env` file into environment
- Used as: `load_dotenv()` at the start of the file
- Allows storing configuration separately from code
- `.env` file contains: `DATABASE_URL=mysql+pymysql://...`
- Never commit `.env` to version control (contains secrets)

---

## 5. Database Models Explained

### What are Models?

Models are Python classes that represent database tables. SQLAlchemy automatically converts these classes to SQL tables.

### Model 1: User (Staff)

```python
class User(UserMixin, db.Model):
    __tablename__ = 'staff'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    contact_no = db.Column(db.String(20))
    email = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    
    sales = db.relationship('Sale', backref='staff', lazy=True)
```

**Detailed Explanation:**

1. **`class User(UserMixin, db.Model)`**:
   - Inherits from `UserMixin` (Flask-Login authentication methods)
   - Inherits from `db.Model` (SQLAlchemy base class for database tables)

2. **`__tablename__ = 'staff'`**:
   - Specifies the actual database table name
   - Table will be called `staff` in MySQL
   - Without this, SQLAlchemy would use `user` (class name)

3. **`id = db.Column(db.Integer, primary_key=True)`**:
   - Creates an integer column that auto-increments
   - `primary_key=True` means it uniquely identifies each row
   - MySQL will create: `id INT AUTO_INCREMENT PRIMARY KEY`

4. **`name = db.Column(db.String(100), nullable=False)`**:
   - Creates a VARCHAR(100) column
   - `nullable=False` means this field is required
   - Cannot be NULL in database

5. **`email = db.Column(db.String(100), unique=True, nullable=False)`**:
   - `unique=True` ensures no two users have the same email
   - Database will enforce uniqueness constraint

6. **`password_hash = db.Column(db.String(128))`**:
   - Stores the hashed password (not plain text!)
   - 128 characters is enough for PBKDF2 hash

7. **`sales = db.relationship('Sale', backref='staff', lazy=True)`**:
   - Creates a relationship to `Sale` model
   - `backref='staff'` means `Sale` objects can access `sale.staff`
   - `lazy=True` means sales are loaded only when accessed
   - Allows: `user.sales` to get all sales by this user

**Methods:**

```python
def set_password(self, password):
    self.password_hash = generate_password_hash(password)
```
- Hashes password before storing
- Called when creating/updating user

```python
def check_password(self, password):
    return check_password_hash(self.password_hash, password)
```
- Verifies password during login
- Compares entered password with stored hash

### Model 2: Part

```python
class Part(db.Model):
    __tablename__ = 'parts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    part_type = db.Column(db.String(50))
    brand = db.Column(db.String(50))
    price = db.Column(db.Float, nullable=False)
    stock_quantity = db.Column(db.Integer, default=0)
    
    stock_entries = db.relationship('StockEntry', backref='part', lazy=True)
    sale_details = db.relationship('SaleDetail', backref='part', lazy=True)
    suppliers = db.relationship('Supplier', secondary='supplier_part', back_populates='parts')
```

**Key Features:**

1. **`price = db.Column(db.Float, nullable=False)`**:
   - Stores decimal prices (e.g., 100.50)
   - `Float` in SQLAlchemy maps to `DECIMAL` or `FLOAT` in MySQL

2. **`stock_quantity = db.Column(db.Integer, default=0)`**:
   - `default=0` means new parts start with 0 stock
   - Can be updated when parts are added/sold

3. **`suppliers = db.relationship('Supplier', secondary='supplier_part', ...)`**:
   - **Many-to-Many relationship**
   - One part can have multiple suppliers
   - One supplier can supply multiple parts
   - `secondary='supplier_part'` refers to the association table

### Model 3: Sale (Transaction)

```python
class Sale(db.Model):
    __tablename__ = 'sales'
    id = db.Column(db.Integer, primary_key=True)
    sale_date = db.Column(db.DateTime, default=datetime.utcnow)
    total_amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    
    details = db.relationship('SaleDetail', backref='sale', lazy=True, cascade='all, delete-orphan')
```

**Key Features:**

1. **`sale_date = db.Column(db.DateTime, default=datetime.utcnow)`**:
   - Automatically sets current time when sale is created
   - `datetime.utcnow` is a function reference (not called immediately)

2. **`staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)`**:
   - **Foreign Key**: Links to `staff` table
   - Ensures staff_id exists in staff table
   - Database enforces referential integrity

3. **`cascade='all, delete-orphan'`**:
   - When a sale is deleted, all related `SaleDetail` records are deleted
   - Prevents orphaned records

### Model 4: SaleDetail (Many-to-Many with Composite Key)

```python
class SaleDetail(db.Model):
    __tablename__ = 'sale_details'
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), primary_key=True)
    part_id = db.Column(db.Integer, db.ForeignKey('parts.id'), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_sale = db.Column(db.Float, nullable=False)
```

**Key Feature: Composite Primary Key**

- **Both `sale_id` and `part_id` are primary keys**
- This means: One sale can have multiple parts, and each part can appear once per sale
- Represents: "Sale #1 contains 2x Part #5 and 1x Part #3"

### Association Table (Many-to-Many)

```python
supplier_part = db.Table('supplier_part',
    db.Column('supplier_id', db.Integer, db.ForeignKey('suppliers.id'), primary_key=True),
    db.Column('part_id', db.Integer, db.ForeignKey('parts.id'), primary_key=True)
)
```

**Why it's needed:**
- Links `suppliers` and `parts` tables
- Stores which suppliers provide which parts
- Composite primary key ensures unique combinations

---

## 6. MySQL Connection Process

### Step-by-Step: How We Connected to MySQL

#### Step 1: MySQL-Only Configuration

The application **requires MySQL** - there is no SQLite fallback. This ensures:
- **Production Ready**: No development-only fallbacks
- **Advanced Features**: Full support for stored procedures, functions, triggers
- **Better Performance**: Optimized for concurrent users
- **Data Integrity**: Better transaction support
- **Scalability**: Can handle larger datasets

#### Step 2: MySQL Connection Setup

The code is configured to require MySQL connection:

```python
# Load environment variables
load_dotenv()

# MySQL connection configuration - REQUIRED
# Connection string format: mysql+pymysql://username:password@host:port/database_name
database_url = os.getenv('DATABASE_URL')

if not database_url:
    # Build connection string from individual MySQL environment variables
    mysql_host = os.getenv('MYSQL_HOST', 'localhost')
    mysql_port = os.getenv('MYSQL_PORT', '3306')
    mysql_user = os.getenv('MYSQL_USER')
    mysql_password = os.getenv('MYSQL_PASSWORD')
    mysql_database = os.getenv('MYSQL_DATABASE')
    
    if mysql_user and mysql_password and mysql_database:
        database_url = f'mysql+pymysql://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}'
    else:
        # MySQL connection is REQUIRED - no fallback to SQLite
        raise ValueError(
            "MySQL database connection is required. Please set either:\n"
            "  - DATABASE_URL environment variable, OR\n"
            "  - MYSQL_USER, MYSQL_PASSWORD, and MYSQL_DATABASE environment variables\n"
            "Example: DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/jrf_motorshop"
        )

# Validate that we're using MySQL (not SQLite)
if not database_url.startswith('mysql'):
    raise ValueError(
        f"Invalid database connection. MySQL is required, but got: {database_url.split('://')[0]}\n"
        "Please configure MySQL connection in your .env file."
    )

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
```

**Detailed Explanation:**

1. **`load_dotenv()`**:
   - Loads variables from `.env` file
   - Makes them available via `os.getenv()`

2. **Connection String Format**:
   ```
   mysql+pymysql://username:password@host:port/database_name
   ```
   - `mysql+pymysql`: Database dialect + driver
   - `username:password`: MySQL credentials
   - `host:port`: Server location (default: localhost:3306)
   - `database_name`: Name of the database

3. **Why `pymysql`?**:
   - Pure Python MySQL connector
   - No C dependencies (easier to install)
   - Compatible with SQLAlchemy

4. **Validation Logic**:
   - If no MySQL config → raises ValueError with clear error message
   - Validates connection string starts with 'mysql'
   - Ensures MySQL is configured before application starts
   - No fallback - MySQL is mandatory

#### Step 3: Installing PyMySQL

Added to `requirements.txt`:
```txt
pymysql==1.1.0
```

**Installation:**
```bash
pip install pymysql
```

#### Step 4: Creating .env File

Created `.env` file with MySQL credentials:

```env
DATABASE_URL=mysql+pymysql://root:password@localhost:3306/jrf_motorshop
```

**OR using individual variables:**
```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=jrf_motorshop
```

#### Step 5: Creating MySQL Database

Before connecting, the database must exist:

```sql
CREATE DATABASE jrf_motorshop CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

**Why utf8mb4?**
- Supports full Unicode (emojis, special characters)
- Required for international text

#### Step 6: Initializing Tables

Running `init_db.py` creates all tables:

```python
with app.app_context():
    db.create_all()  # Creates all tables defined in models
```

**What happens:**
- SQLAlchemy reads all `db.Model` classes
- Generates `CREATE TABLE` statements
- Executes them in MySQL
- Creates: `staff`, `parts`, `sales`, `sale_details`, etc.

#### Step 7: Verifying Connection

We created test scripts to verify:

```python
# test_db_connection.py
from app import app, db

with app.app_context():
    db.engine.connect()  # Tests connection
    # Query tables
    tables = db.inspect(db.engine).get_table_names()
```

---

## 7. Database Objects Implementation

### Why Database Objects?

Database objects (functions, stored procedures, triggers) move logic from application code to the database, providing:
- **Performance**: Executed on database server (faster)
- **Consistency**: Same logic for all applications
- **Security**: Can restrict access at database level

### 7.1 Functions

#### Function 1: CalculateDiscount

```sql
CREATE FUNCTION CalculateDiscount(
    price DECIMAL(10, 2),
    discount_percent DECIMAL(5, 2)
) RETURNS DECIMAL(10, 2)
```

**What it does:**
- Calculates discount amount from price and percentage
- Returns the discount value (not final price)

**Why it's a function:**
- Reusable calculation
- Can be used in SELECT statements
- Example: `SELECT CalculateDiscount(1000, 10)` → returns `100.00`

**Usage in Python:**
```python
result = db.session.execute(
    db.text('SELECT CalculateDiscount(:price, :discount)'),
    {'price': 1000.00, 'discount': 10.00}
)
discount = result.scalar()  # Returns 100.00
```

#### Function 2: GetStockStatus

```sql
CREATE FUNCTION GetStockStatus(stock_quantity INT) RETURNS VARCHAR(10)
```

**What it does:**
- Returns status string based on quantity:
  - 0 → 'Out'
  - 1-4 → 'Low'
  - 5-19 → 'Medium'
  - 20+ → 'High'

**Why it's useful:**
- Consistent status calculation
- Can be used in queries: `SELECT GetStockStatus(stock_quantity) FROM parts`

#### Function 3: FormatCurrency

```sql
CREATE FUNCTION FormatCurrency(amount DECIMAL(10, 2)) RETURNS VARCHAR(20)
```

**What it does:**
- Formats number as currency: `1234.56` → `'₱1,234.56'`

**Why it's useful:**
- Consistent formatting across application
- Can format in SQL queries before sending to frontend

### 7.2 Stored Procedures

#### Stored Procedure 1: GetLowStockParts

```sql
CREATE PROCEDURE GetLowStockParts(IN threshold INT)
BEGIN
    SELECT id, name, part_type, brand, price, stock_quantity, description
    FROM parts
    WHERE stock_quantity < threshold
    ORDER BY stock_quantity ASC, name ASC;
END
```

**What it does:**
- Returns all parts below a threshold
- Sorted by stock quantity (lowest first)

**Why it's a stored procedure:**
- Complex query logic
- Can be optimized by database
- Reusable across applications

**Usage in Python:**
```python
result = db.session.execute(
    db.text('CALL GetLowStockParts(:threshold)'),
    {'threshold': 5}
)
parts = result.fetchall()
```

#### Stored Procedure 2: CalculateMonthlySales

```sql
CREATE PROCEDURE CalculateMonthlySales(
    IN p_year INT,
    IN p_month INT,
    OUT total_sales DECIMAL(10, 2),
    OUT total_count INT
)
```

**What it does:**
- Calculates sales totals for a specific month
- Returns two values: total amount and count

**Why OUTPUT parameters:**
- Stored procedures can return multiple values
- More efficient than returning result set for simple calculations

**Usage in Python:**
```python
# Call procedure
db.session.execute(
    db.text('CALL CalculateMonthlySales(:year, :month, @total, @count)'),
    {'year': 2024, 'month': 1}
)
# Get output parameters
result = db.session.execute(db.text('SELECT @total, @count'))
total, count = result.fetchone()
```

### 7.3 Triggers

#### Trigger 1: trg_update_stock_after_sale

```sql
CREATE TRIGGER trg_update_stock_after_sale
AFTER INSERT ON sale_details
FOR EACH ROW
BEGIN
    UPDATE parts
    SET stock_quantity = stock_quantity - NEW.quantity
    WHERE id = NEW.part_id;
END
```

**What it does:**
- **Automatically** decreases stock when a sale detail is inserted
- No need to manually update stock in application code

**Why it's useful:**
- **Data integrity**: Stock always matches sales
- **Automatic**: Can't forget to update stock
- **Atomic**: Happens in same transaction

**How it works:**
1. User creates a sale with parts
2. `SaleDetail` records are inserted
3. **Trigger fires automatically**
4. Stock quantities are updated
5. All in one transaction (all or nothing)

#### Trigger 2: trg_log_stock_entry

```sql
CREATE TRIGGER trg_log_stock_entry
AFTER UPDATE ON parts
FOR EACH ROW
BEGIN
    IF OLD.stock_quantity != NEW.stock_quantity THEN
        INSERT INTO stock_entries (part_id, quantity, entry_date)
        VALUES (NEW.id, NEW.stock_quantity - OLD.stock_quantity, NOW());
    END IF;
END
```

**What it does:**
- **Automatically** logs every stock change
- Creates audit trail in `stock_entries` table

**Why it's useful:**
- **Audit trail**: Track all stock changes
- **Automatic**: No need to remember to log
- **Complete history**: Every change is recorded

#### Trigger 3: trg_prevent_negative_stock

```sql
CREATE TRIGGER trg_prevent_negative_stock
BEFORE UPDATE ON parts
FOR EACH ROW
BEGIN
    IF NEW.stock_quantity < 0 THEN
        SET NEW.stock_quantity = 0;
    END IF;
END
```

**What it does:**
- **Prevents** negative stock quantities
- Sets to 0 if update would make it negative

**Why it's useful:**
- **Data integrity**: Stock can never be negative
- **Business rule enforcement**: At database level

---

## 8. Role-Based Access Control (RBAC)

### What is RBAC?

**Role-Based Access Control (RBAC)** is a security model that restricts system access based on user roles. Instead of checking individual permissions for each user, we assign roles (admin, manager, staff) and grant permissions to roles.

### Why RBAC is Important

1. **Security**: Prevents unauthorized access to sensitive features
2. **Scalability**: Easy to add new roles without changing code
3. **Maintainability**: Centralized permission logic
4. **User Experience**: Users only see features they can access

### User Roles in the System

The system supports three roles:

1. **Admin** (`role = 'admin'`)
   - Full system access
   - Can manage staff, inventory, suppliers, reports
   - Highest privilege level

2. **Manager** (`role = 'manager'`)
   - Management access
   - Can manage inventory, suppliers, view reports
   - Cannot manage staff

3. **Staff** (`role = 'staff'`)
   - Limited access
   - Can view inventory and process sales
   - Cannot edit inventory, manage suppliers, or view reports

### Role Permissions Matrix

| Feature | Admin | Manager | Staff |
|---------|-------|---------|-------|
| View Dashboard | ✅ | ✅ | ✅ |
| View Inventory | ✅ | ✅ | ✅ |
| Add/Edit/Delete Parts | ✅ | ✅ | ❌ |
| Process Sales | ✅ | ✅ | ✅ |
| View Suppliers | ✅ | ✅ | ❌ |
| Manage Suppliers | ✅ | ✅ | ❌ |
| View Reports | ✅ | ✅ | ❌ |
| Manage Staff | ✅ | ❌ | ❌ |
| View Settings | ✅ | ✅ | ✅ |

### Implementation: User Model Methods

We added role-checking methods to the `User` model:

```python
class User(UserMixin, db.Model):
    # ... existing fields ...
    role = db.Column(db.String(50), nullable=False)
    
    # Role checking methods
    def is_admin(self):
        """Check if user has admin role"""
        return self.role == 'admin'
    
    def is_manager(self):
        """Check if user has manager role"""
        return self.role == 'manager'
    
    def is_staff(self):
        """Check if user has staff role"""
        return self.role == 'staff'
    
    def has_role(self, *roles):
        """Check if user has any of the specified roles"""
        return self.role in roles
    
    # Permission checking methods
    def can_manage_staff(self):
        """Only admin can manage staff"""
        return self.is_admin()
    
    def can_manage_inventory(self):
        """Admin and manager can manage inventory"""
        return self.is_admin() or self.is_manager()
    
    def can_view_reports(self):
        """Admin and manager can view reports"""
        return self.is_admin() or self.is_manager()
    
    def can_manage_suppliers(self):
        """Admin and manager can manage suppliers"""
        return self.is_admin() or self.is_manager()
```

**Detailed Explanation:**

1. **`is_admin()`, `is_manager()`, `is_staff()`**:
   - Simple boolean checks
   - Return `True` if user has that specific role
   - Used for role-specific logic

2. **`has_role(*roles)`**:
   - Flexible method that accepts multiple roles
   - Returns `True` if user has any of the specified roles
   - Example: `user.has_role('admin', 'manager')` → returns `True` for both admin and manager

3. **Permission Methods** (`can_manage_*`, `can_view_*`):
   - Encapsulate business logic about who can do what
   - Combine role checks with OR logic
   - Example: `can_manage_inventory()` returns `True` for both admin AND manager

**Why This Design?**
- **Separation of Concerns**: Role logic is in the User model
- **Reusability**: Can be called from routes, templates, API endpoints
- **Maintainability**: Change permission logic in one place
- **Readability**: `current_user.can_manage_inventory()` is self-documenting

### Implementation: Route Decorators

We created three decorators to protect routes:

#### 1. `@admin_required` Decorator

```python
def admin_required(f):
    """Decorator to restrict access to admin only"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin():
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function
```

**How it works:**
1. `@wraps(f)` preserves the original function's metadata
2. `@login_required` ensures user is logged in first
3. Checks if `current_user.is_admin()` returns `True`
4. If not admin → flash error message and redirect to dashboard
5. If admin → execute the route function

**Usage:**
```python
@app.route('/staff')
@admin_required
def staff():
    # Only admins can access this route
    staff = User.query.all()
    return render_template('staff.html', staff=staff)
```

#### 2. `@manager_required` Decorator

```python
def manager_required(f):
    """Decorator to restrict access to manager and admin"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not (current_user.is_admin() or current_user.is_manager()):
            flash('Manager access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function
```

**How it works:**
- Similar to `@admin_required` but allows both admin AND manager
- Uses OR logic: `is_admin() OR is_manager()`

**Usage:**
```python
@app.route('/suppliers')
@manager_required
def suppliers():
    # Admins and managers can access
    suppliers = Supplier.query.all()
    return render_template('suppliers.html', suppliers=suppliers)
```

#### 3. `@role_required(*roles)` Decorator

```python
def role_required(*roles):
    """
    Decorator to restrict access to routes based on user roles.
    Usage: @role_required('admin', 'manager')
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.has_role(*roles):
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

**How it works:**
- Takes variable number of roles as arguments
- Uses `has_role(*roles)` to check if user has any of the specified roles
- More flexible than fixed decorators

**Usage:**
```python
@app.route('/reports')
@role_required('admin', 'manager')
def reports():
    # Only admin and manager can access
    return render_template('reports.html')
```

**Why Three Decorators?**
- **`@admin_required`**: Common case, simple and clear
- **`@manager_required`**: Common case (admin + manager)
- **`@role_required`**: Flexible for custom combinations

### Protected Routes

#### Admin-Only Routes

```python
@app.route('/staff')
@admin_required
def staff():
    # Staff management - only admins
    pass

@app.route('/api/staff', methods=['GET', 'POST'])
@admin_required
def handle_staff():
    # Staff API - only admins
    pass
```

**Why admin-only?**
- Staff management is sensitive
- Only system administrators should create/modify user accounts
- Prevents privilege escalation

#### Manager/Admin Routes

```python
@app.route('/suppliers')
@manager_required
def suppliers():
    # Supplier management - managers and admins
    pass

@app.route('/reports')
@manager_required
def reports():
    # Reports - managers and admins
    pass

@app.route('/api/sales-data')
@manager_required
def get_sales_data():
    # Sales analytics - managers and admins
    pass
```

**Why manager/admin?**
- Management-level features
- Staff don't need to see business analytics
- Suppliers are management concern

#### All Authenticated Users

```python
@app.route('/dashboard')
@login_required
def index():
    # All logged-in users can access
    pass

@app.route('/inventory')
@login_required
def inventory():
    # All users can view inventory
    # But only manager/admin can edit (handled in template/API)
    pass

@app.route('/sales')
@login_required
def sales():
    # All users can process sales
    pass
```

### API Endpoint Restrictions

Some API endpoints have **partial restrictions** - they allow GET for all users but restrict POST/PUT/DELETE:

#### Example: `/api/parts` Endpoint

```python
@app.route('/api/parts', methods=['GET', 'POST'])
@login_required
def handle_parts():
    if request.method == 'GET':
        # All authenticated users can view parts
        parts = Part.query.all()
        return jsonify([{...} for part in parts])
    
    # POST - Add new part (admin/manager only)
    if not current_user.can_manage_inventory():
        return jsonify({
            'success': False, 
            'message': 'Permission denied. Admin or Manager access required.'
        }), 403
    
    # Only reaches here if user has permission
    data = request.get_json()
    new_part = Part(...)
    db.session.add(new_part)
    db.session.commit()
    return jsonify({'success': True}), 201
```

**Why this approach?**
- **GET requests**: All users need to view inventory
- **POST/PUT/DELETE**: Only managers/admins should modify
- **403 Forbidden**: Standard HTTP status for permission denied
- **Clear error message**: Tells user why access was denied

#### Example: `/api/parts/<id>` Endpoint

```python
@app.route('/api/parts/<int:part_id>', methods=['PUT', 'DELETE'])
@login_required
def handle_part(part_id):
    # Only admin/manager can edit/delete parts
    if not current_user.can_manage_inventory():
        return jsonify({
            'success': False, 
            'message': 'Permission denied. Admin or Manager access required.'
        }), 403
    
    part = Part.query.get_or_404(part_id)
    
    if request.method == 'PUT':
        # Update part
        pass
    elif request.method == 'DELETE':
        # Delete part
        pass
```

### Template-Based Access Control

#### Context Processor

We added a context processor to make role checks available in all templates:

```python
@app.context_processor
def inject_user_permissions():
    """Make user role and permissions available in all templates"""
    if current_user.is_authenticated:
        return {
            'user_role': current_user.role,
            'is_admin': current_user.is_admin(),
            'is_manager': current_user.is_manager(),
            'is_staff': current_user.is_staff(),
            'can_manage_staff': current_user.can_manage_staff(),
            'can_manage_inventory': current_user.can_manage_inventory(),
            'can_view_reports': current_user.can_view_reports(),
            'can_manage_suppliers': current_user.can_manage_suppliers()
        }
    return {}
```

**What this does:**
- Runs before every template render
- Injects permission variables into template context
- Available in ALL templates automatically

**Usage in templates:**
```jinja2
{% if is_admin %}
    <!-- Admin-only content -->
{% endif %}

{% if can_manage_inventory %}
    <button>Add Part</button>
{% endif %}
```

#### Navigation Menu (Sidebar)

The sidebar in `base_new.html` conditionally shows menu items:

```jinja2
<!-- Always visible -->
<a href="{{ url_for('index') }}">Dashboard</a>
<a href="{{ url_for('inventory') }}">Inventory</a>
<a href="{{ url_for('sales') }}">Sales</a>

<!-- Conditionally visible based on role -->
{% if current_user.can_manage_suppliers() %}
<a href="{{ url_for('suppliers') }}">Suppliers</a>
{% endif %}

{% if current_user.can_manage_staff() %}
<a href="{{ url_for('staff') }}">Staff</a>
{% endif %}

{% if current_user.can_view_reports() %}
<a href="{{ url_for('reports') }}">Reports</a>
{% endif %}

<!-- Always visible -->
<a href="{{ url_for('settings') }}">Settings</a>
```

**Why hide menu items?**
- **Better UX**: Users don't see features they can't use
- **Security**: Even if they try to access via URL, route decorator blocks them
- **Cleaner interface**: Less clutter for lower-privilege users

#### Inventory Page

The inventory page hides edit/delete buttons for staff:

```jinja2
<!-- Add Part Button -->
{% if current_user.can_manage_inventory() %}
<button id="addPartBtn" class="...">
    <i class="fas fa-plus"></i> Add Part
</button>
{% endif %}

<!-- In the table, for each part -->
{% if current_user.can_manage_inventory() %}
<button data-action="edit" data-part-id="{{ part.id }}">
    <i class="fas fa-edit"></i>
</button>
<button data-action="delete" data-part-id="{{ part.id }}">
    <i class="fas fa-trash"></i>
</button>
{% else %}
<span class="text-gray-400 text-xs">View Only</span>
{% endif %}
```

**Why this matters:**
- Staff can view inventory but cannot modify
- Prevents accidental clicks on disabled features
- Clear indication of "View Only" status

### Multi-Layer Security

The RBAC system uses **three layers of protection**:

#### Layer 1: Route Decorators
- **First line of defense**
- Blocks unauthorized access at the route level
- Redirects with error message if unauthorized
- **Example**: `@admin_required` on `/staff` route

#### Layer 2: API Endpoint Checks
- **Second line for dynamic requests**
- Checks permissions inside route handlers
- Returns 403 Forbidden for unauthorized API calls
- **Example**: Check `can_manage_inventory()` before POST to `/api/parts`

#### Layer 3: Template Conditions
- **UI/UX improvement**
- Hides features from unauthorized users
- Prevents confusion and accidental clicks
- **Example**: `{% if can_manage_inventory %}` around edit buttons

**Why three layers?**
- **Defense in depth**: If one layer fails, others protect
- **Route decorators**: Prevent direct URL access
- **API checks**: Prevent programmatic access (AJAX/fetch)
- **Template conditions**: Improve user experience

### Error Handling

#### Route Access Errors

When a user tries to access a restricted route:

```python
@admin_required
def staff():
    # If not admin, decorator executes:
    flash('Admin access required.', 'error')
    return redirect(url_for('index'))
```

**What happens:**
1. User (staff role) tries to visit `/staff`
2. `@admin_required` decorator checks `current_user.is_admin()`
3. Returns `False` (user is staff, not admin)
4. Flash message stored: "Admin access required."
5. User redirected to dashboard
6. Dashboard displays flash message

#### API Access Errors

When a user tries to access a restricted API endpoint:

```python
if not current_user.can_manage_inventory():
    return jsonify({
        'success': False, 
        'message': 'Permission denied. Admin or Manager access required.'
    }), 403
```

**What happens:**
1. Frontend JavaScript makes POST request to `/api/parts`
2. Route handler checks `can_manage_inventory()`
3. Returns `False` (user is staff)
4. Returns JSON response with `success: False` and HTTP 403
5. Frontend JavaScript receives error
6. Displays error message to user

**HTTP Status Codes:**
- **200 OK**: Request successful
- **201 Created**: Resource created successfully
- **403 Forbidden**: Permission denied (used for RBAC)
- **404 Not Found**: Resource doesn't exist
- **500 Internal Server Error**: Server error

### Testing Role-Based Access

#### Test as Admin

1. **Login**: `admin@jrfmotorcycle.com` / `admin123`
2. **Expected Menu Items**: Dashboard, Inventory, Sales, Suppliers, Staff, Reports, Settings
3. **Can Do**:
   - Add/edit/delete parts
   - Manage suppliers
   - Manage staff (add/edit/delete users)
   - View reports
   - Process sales

#### Test as Manager

1. **Login**: `john.smith@jrfmotorcycle.com` / `password123`
2. **Expected Menu Items**: Dashboard, Inventory, Sales, Suppliers, Reports, Settings (NO Staff)
3. **Can Do**:
   - Add/edit/delete parts
   - Manage suppliers
   - View reports
   - Process sales
4. **Cannot Do**:
   - Access `/staff` route (redirected with error)
   - Manage staff via API (403 Forbidden)

#### Test as Staff

1. **Login**: `sarah.johnson@jrfmotorcycle.com` / `password123`
2. **Expected Menu Items**: Dashboard, Inventory, Sales, Settings (NO Suppliers, Staff, Reports)
3. **Can Do**:
   - View inventory (read-only)
   - Process sales
   - View dashboard
4. **Cannot Do**:
   - Add/edit/delete parts (buttons hidden, API returns 403)
   - Access suppliers page (redirected)
   - Access reports page (redirected)
   - Access staff page (redirected)

### Adding New Roles

To add a new role (e.g., "supervisor"):

#### Step 1: Add Role to Database

Update existing users or create new ones with `role = 'supervisor'`

#### Step 2: Add Method to User Model

```python
def is_supervisor(self):
    """Check if user has supervisor role"""
    return self.role == 'supervisor'
```

#### Step 3: Add Permission Methods

```python
def can_approve_orders(self):
    """Supervisor and above can approve orders"""
    return self.is_admin() or self.is_manager() or self.is_supervisor()
```

#### Step 4: Create Decorator (Optional)

```python
def supervisor_required(f):
    """Decorator for supervisor and above"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not (current_user.is_admin() or current_user.is_manager() or current_user.is_supervisor()):
            flash('Supervisor access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function
```

#### Step 5: Apply to Routes

```python
@app.route('/orders')
@supervisor_required
def orders():
    # Supervisor, manager, and admin can access
    pass
```

#### Step 6: Update Templates

```jinja2
{% if current_user.can_approve_orders() %}
<a href="{{ url_for('orders') }}">Orders</a>
{% endif %}
```

#### Step 7: Update Context Processor

Add to `inject_user_permissions()`:
```python
'is_supervisor': current_user.is_supervisor(),
'can_approve_orders': current_user.can_approve_orders()
```

### Best Practices

1. **Always use decorators** on routes that need protection
   - Don't rely only on template hiding
   - Route decorators are the primary security

2. **Check permissions in API endpoints** for dynamic operations
   - Even if route allows access, check permissions for POST/PUT/DELETE
   - Return appropriate HTTP status codes (403 Forbidden)

3. **Hide UI elements** in templates for better UX
   - Users shouldn't see features they can't use
   - Reduces confusion and support requests

4. **Test with different roles** to ensure proper restrictions
   - Create test accounts for each role
   - Verify menu items, buttons, and API access

5. **Use descriptive error messages** when access is denied
   - Tell users why they can't access a feature
   - Suggest what role they need

6. **Centralize permission logic** in User model
   - Don't duplicate role checks
   - Use methods like `can_manage_inventory()` everywhere

### Summary: RBAC Implementation

The role-based access control system provides:

- ✅ **Security**: Multi-layer protection (route, API, template)
- ✅ **Flexibility**: Easy to add new roles and permissions
- ✅ **User Experience**: Clean UI showing only relevant features
- ✅ **Maintainability**: Centralized permission logic in User model
- ✅ **Scalability**: Can handle complex permission hierarchies

**Key Components:**
1. User model methods for role/permission checks
2. Route decorators for access control
3. API endpoint permission checks
4. Template conditions for UI visibility
5. Context processor for template access

All routes, API endpoints, and UI elements are now properly protected based on user roles!

---

## 9. API Endpoints and Routes

### Route Types

#### 1. Page Routes (Return HTML)

```python
@app.route('/dashboard')
@login_required
def index():
    # Query database
    total_parts = Part.query.count()
    # Render HTML template
    return render_template('dashboard.html', total_parts=total_parts)
```

**Flow:**
1. User visits `/dashboard`
2. `@login_required` checks authentication
3. Function queries database
4. Renders HTML template with data
5. Browser displays page

#### 2. API Routes (Return JSON)

```python
@app.route('/api/parts', methods=['GET', 'POST'])
@login_required
def handle_parts():
    if request.method == 'GET':
        parts = Part.query.all()
        return jsonify([{...} for part in parts])
```

**Flow:**
1. Frontend JavaScript makes fetch request
2. Route handler queries database
3. Returns JSON data
4. JavaScript updates page dynamically

### Key Endpoints Explained

#### Endpoint: `/api/sales` (POST) - Transaction Example

```python
@app.route('/api/sales', methods=['POST'])
@login_required
def process_sale():
    try:
        data = request.get_json()  # Get JSON from frontend
        
        # Create sale record
        new_sale = Sale(
            staff_id=current_user.id,
            total_amount=float(data['total']),
            payment_method=data['paymentMethod']
        )
        db.session.add(new_sale)
        db.session.flush()  # Get ID without committing
        
        # Add sale details and update stock
        for item in data['items']:
            # Create sale detail (triggers will fire here!)
            sale_detail = SaleDetail(...)
            db.session.add(sale_detail)
            
            # Update stock (though trigger also does this)
            part = Part.query.get(item['id'])
            part.stock_quantity -= item['quantity']
        
        db.session.commit()  # Commit entire transaction
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()  # Undo all changes on error
        return jsonify({'success': False}), 500
```

**Transaction Flow:**
1. **Begin Transaction** (implicit when first `add()` is called)
2. Add sale record
3. Add sale detail records (triggers fire)
4. Update stock quantities
5. **Commit** (saves all changes) OR **Rollback** (undoes all changes)

**Why transactions?**
- **Atomicity**: All or nothing
- If stock update fails, sale is not created
- Prevents inconsistent data

#### Endpoint: `/api/low-stock-parts` - Using Stored Procedure

```python
@app.route('/api/low-stock-parts', methods=['GET'])
@login_required
def get_low_stock_parts():
    threshold = int(request.args.get('threshold', 5))
    
    # Call stored procedure
    result = db.session.execute(
        db.text('CALL GetLowStockParts(:threshold)'),
        {'threshold': threshold}
    )
    
    # Process results
    parts = []
    for row in result:
        # Call function for each part
        status = db.session.execute(
            db.text('SELECT GetStockStatus(:qty)'),
            {'qty': row[5]}
        ).scalar()
        
        parts.append({
            'id': row[0],
            'name': row[1],
            'stock_status': status
        })
    
    return jsonify(parts)
```

**What happens:**
1. Gets threshold from query parameter
2. Calls stored procedure in MySQL
3. MySQL executes query and returns results
4. For each result, calls function to get status
5. Returns JSON to frontend

---

## 10. Security Implementation

### Password Hashing

**Never store plain passwords!**

```python
# When creating user
user.set_password('admin123')
# Internally calls:
self.password_hash = generate_password_hash('admin123')
# Stores: 'pbkdf2:sha256:260000$salt$hash...'
```

**During login:**
```python
if user.check_password(password):
    # Internally calls:
    check_password_hash(self.password_hash, password)
    # Compares entered password with stored hash
```

**Why PBKDF2?**
- **Slow by design**: Prevents brute force attacks
- **Salted**: Each password has unique salt
- **One-way**: Cannot reverse hash to get password

### Session Management

```python
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
```

**What it does:**
- Creates secure session cookies
- Tracks logged-in users
- Automatically expires sessions

**How it works:**
1. User logs in → `login_user(user)`
2. Flask-Login creates session cookie
3. Cookie sent to browser
4. Browser sends cookie with each request
5. Flask-Login identifies user from cookie
6. `@login_required` checks if user is authenticated

### Route Protection

#### Basic Authentication

```python
@app.route('/dashboard')
@login_required
def index():
    # This code only runs if user is logged in
    return render_template('dashboard.html')
```

**What `@login_required` does:**
- Checks if `current_user.is_authenticated`
- If not → redirects to `/login`
- If yes → allows access to route

#### Role-Based Route Protection

```python
@app.route('/staff')
@admin_required
def staff():
    # This code only runs if user is admin
    return render_template('staff.html')
```

**What `@admin_required` does:**
1. First checks `@login_required` (user must be logged in)
2. Then checks `current_user.is_admin()`
3. If not admin → flash error and redirect to dashboard
4. If admin → allows access to route

**Combined Protection:**
- `@login_required` ensures user is authenticated
- `@admin_required` ensures user has admin role
- Both checks must pass for route to execute

---

## 11. How Everything Works Together

### Complete Request Flow Example: Processing a Sale

#### Step 1: User Action (Frontend)

```javascript
// User clicks "Process Payment" button
fetch('/api/sales', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        items: [{id: 1, quantity: 2, price: 100}],
        total: 200,
        paymentMethod: 'Cash'
    })
})
```

#### Step 2: Flask Receives Request

```python
@app.route('/api/sales', methods=['POST'])
@login_required  # Checks if user is logged in
def process_sale():
```

**What happens:**
- Flask receives HTTP POST request
- `@login_required` checks session cookie
- If authenticated → proceed
- If not → return 401 Unauthorized

**Note**: Sales processing is available to all authenticated users (admin, manager, staff). For role-restricted endpoints, additional checks occur:

```python
@app.route('/api/parts', methods=['POST'])
@login_required
def handle_parts():
    # First: @login_required ensures user is authenticated
    # Then: Check if user can manage inventory
    if not current_user.can_manage_inventory():
        return jsonify({'success': False, 'message': 'Permission denied.'}), 403
    # Only admin/manager reach here
```

#### Step 3: Parse Request Data

```python
data = request.get_json()
# data = {
#     'items': [{'id': 1, 'quantity': 2, 'price': 100}],
#     'total': 200,
#     'paymentMethod': 'Cash'
# }
```

#### Step 4: Begin Database Transaction

```python
new_sale = Sale(...)
db.session.add(new_sale)
db.session.flush()  # Gets ID but doesn't commit yet
```

**Transaction starts here** (implicit)

#### Step 5: Process Each Item

```python
for item in data['items']:
    # Create sale detail
    sale_detail = SaleDetail(...)
    db.session.add(sale_detail)
    
    # TRIGGER FIRES HERE!
    # trg_update_stock_after_sale automatically runs:
    # UPDATE parts SET stock_quantity = stock_quantity - 2 WHERE id = 1
```

**What the trigger does:**
- Automatically executes SQL
- Updates stock quantity
- All within the same transaction

#### Step 6: Commit Transaction

```python
db.session.commit()
```

**What happens:**
- All changes are saved to MySQL
- Sale record created
- Sale detail records created
- Stock quantities updated (by trigger)
- All or nothing: if any step fails, everything is rolled back

#### Step 7: Return Response

```python
return jsonify({'success': True, 'sale_id': new_sale.id})
```

#### Step 8: Frontend Updates

```javascript
// JavaScript receives response
.then(response => response.json())
.then(data => {
    if (data.success) {
        // Show success message
        // Clear cart
        // Refresh inventory
    }
})
```

### Database Query Flow

#### Example: Getting Low Stock Parts

```python
# 1. Python code calls stored procedure
result = db.session.execute(
    db.text('CALL GetLowStockParts(:threshold)'),
    {'threshold': 5}
)

# 2. SQLAlchemy sends SQL to MySQL
# SQL: CALL GetLowStockParts(5)

# 3. MySQL executes stored procedure
# SELECT * FROM parts WHERE stock_quantity < 5

# 4. MySQL returns results to SQLAlchemy

# 5. SQLAlchemy converts to Python objects

# 6. Python processes results
for row in result:
    # row is a tuple: (id, name, part_type, ...)
    parts.append({'id': row[0], 'name': row[1]})

# 7. Convert to JSON
return jsonify(parts)

# 8. Flask sends JSON response to browser
```

### Model Relationships in Action

```python
# Get a user
user = User.query.get(1)

# Access related sales (one-to-many)
sales = user.sales  # Returns list of Sale objects
# SQL generated: SELECT * FROM sales WHERE staff_id = 1

# Access staff from sale (many-to-one)
sale = Sale.query.get(1)
staff_name = sale.staff.name  # Uses backref
# SQL generated: SELECT * FROM staff WHERE id = sale.staff_id

# Access parts from supplier (many-to-many)
supplier = Supplier.query.get(1)
parts = supplier.parts  # Returns list of Part objects
# SQL generated: 
# SELECT parts.* FROM parts 
# JOIN supplier_part ON parts.id = supplier_part.part_id
# WHERE supplier_part.supplier_id = 1
```

---

## Summary: Complete Project Flow

### Initialization (First Run)

1. **Install dependencies**: `pip install -r requirements.txt`
   - This installs PyMySQL and all required packages
   
2. **Create MySQL database**: 
   ```sql
   CREATE DATABASE jrf_motorshop CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
   - **MySQL is required** - application will not start without it
   
3. **Create `.env` file**: Add MySQL credentials
   ```env
   DATABASE_URL=mysql+pymysql://username:password@localhost:3306/jrf_motorshop
   ```
   - **Required**: Application validates MySQL connection on startup
   - If MySQL not configured, raises `ValueError` with clear instructions
   
4. **Run `init_db.py`**: Creates tables and sample data
   - Creates all database tables in MySQL
   - Creates admin, manager, and staff users
   - Adds sample parts and suppliers
   
5. **Run `setup_database_objects.py`**: Creates functions, procedures, triggers
   - Creates 3 stored procedures
   - Creates 3 functions
   - Creates 3 triggers
   - **Requires MySQL** - these features don't work with SQLite
   
6. **Start application**: `python app.py`
   - Application validates MySQL connection
   - If connection fails, application won't start
   - All database operations use MySQL

### Normal Operation

1. **User visits site** → Flask serves login page
2. **User logs in** → Flask-Login creates session
3. **User navigates** → Flask checks `@login_required`
4. **User views data** → Flask queries MySQL via SQLAlchemy
5. **User creates sale** → Flask processes in transaction
6. **Triggers fire** → MySQL automatically updates stock
7. **Response sent** → Frontend updates display

### Data Flow

```
Browser → Flask App → SQLAlchemy ORM → PyMySQL Driver → MySQL Database
                                                              ↓
                                                         Triggers Execute
                                                              ↓
Browser ← JSON/HTML ← Flask App ← SQLAlchemy ORM ← PyMySQL Driver ← MySQL Database
```

---

## Key Takeaways

1. **Flask** provides the web framework
2. **SQLAlchemy** provides database abstraction (ORM)
3. **PyMySQL** provides MySQL connectivity (required - no fallback)
4. **Flask-Login** provides authentication
5. **Werkzeug** provides password hashing
6. **python-dotenv** loads configuration
7. **Database objects** (functions, procedures, triggers) move logic to database
8. **Transactions** ensure data consistency
9. **Models** represent database tables as Python classes
10. **Relationships** connect models (one-to-many, many-to-many)
11. **Role-Based Access Control (RBAC)** provides multi-layer security
12. **Route decorators** protect routes based on user roles
13. **Template conditions** provide role-based UI visibility
14. **Context processors** make role checks available in all templates

## Complete Request Flow with RBAC

### Example: Staff User Trying to Add a Part

#### Step 1: User Action
```javascript
// Staff user clicks "Add Part" button (if visible due to bug)
fetch('/api/parts', {
    method: 'POST',
    body: JSON.stringify({name: 'New Part', price: 100})
})
```

#### Step 2: Route Handler
```python
@app.route('/api/parts', methods=['POST'])
@login_required  # ✅ Passes - user is logged in
def handle_parts():
    # Permission check
    if not current_user.can_manage_inventory():
        # ❌ Staff user fails this check
        return jsonify({
            'success': False, 
            'message': 'Permission denied. Admin or Manager access required.'
        }), 403
```

#### Step 3: Response
- Frontend receives 403 Forbidden
- Error message displayed to user
- Part is NOT created

**Why this works:**
- Even if button is visible (template bug), API blocks the request
- Multi-layer security: template + API check
- Clear error message explains why access was denied

### Example: Manager Accessing Reports

#### Step 1: User Navigation
- Manager clicks "Reports" in sidebar
- Browser requests `/reports`

#### Step 2: Route Protection
```python
@app.route('/reports')
@manager_required  # Checks: is_admin() OR is_manager()
def reports():
    # ✅ Manager passes check
    return render_template('reports.html')
```

#### Step 3: Template Rendering
- Template has access to `can_view_reports` (from context processor)
- Reports page renders with full functionality
- Manager can view all reports

### Example: Staff User Trying Direct URL Access

#### Step 1: User Action
- Staff user types `/staff` in browser address bar
- Attempts to access admin-only route

#### Step 2: Route Protection
```python
@app.route('/staff')
@admin_required  # Checks: is_admin()
def staff():
    # ❌ Staff user fails check
    # Decorator executes:
    flash('Admin access required.', 'error')
    return redirect(url_for('index'))
```

#### Step 3: Redirect
- User redirected to dashboard
- Flash message displayed: "Admin access required."
- Staff page never rendered

**Why this works:**
- Route decorator blocks access before function executes
- User cannot bypass by typing URL directly
- Clear feedback about why access was denied

This architecture provides a **scalable, secure, and maintainable** web application for managing a motorcycle parts business with comprehensive role-based access control!

