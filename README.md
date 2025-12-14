# JRF Motorcycle Parts & Accessories System

A comprehensive inventory and sales management system for motorcycle parts and accessories.

## Features

- **Inventory Management**: Add, edit, delete, and search motorcycle parts
- **Sales Management**: Point-of-sale system with cart management and payment processing
- **User Authentication**: Secure login system for staff members
- **Dashboard**: Overview of system statistics and recent activities
- **Modern UI**: Clean, responsive interface using Tailwind CSS

## System Requirements

- Python 3.8 or higher
- pip (Python package manager)
- MySQL Server 5.7 or higher (or MariaDB 10.2+)
- Modern web browser (Chrome, Firefox, Safari, Edge)

## MySQL Database Setup

**MySQL is required** for this application. Follow these steps:

### 1. Install MySQL

- **Windows**: Download from [MySQL Downloads](https://dev.mysql.com/downloads/installer/)
- **macOS**: `brew install mysql` or download installer
- **Linux**: `sudo apt-get install mysql-server` (Ubuntu/Debian) or `sudo yum install mysql-server` (CentOS/RHEL)

### 2. Create Database

Connect to MySQL and create the database:

```sql
CREATE DATABASE jrf_motorshop CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 3. Configure Connection

Create a `.env` file in the project root:

```env
# Flask Configuration
SECRET_KEY=your-secret-key-here-change-in-production

# MySQL Database Connection (Option 1: Full connection string)
DATABASE_URL=mysql+pymysql://username:password@localhost:3306/jrf_motorshop

# OR MySQL Database Connection (Option 2: Individual variables)
# MYSQL_HOST=localhost
# MYSQL_PORT=3306
# MYSQL_USER=your_username
# MYSQL_PASSWORD=your_password
# MYSQL_DATABASE=jrf_motorshop
```

**Important**: Replace `username`, `password`, and `jrf_motorshop` with your actual MySQL credentials and database name.

### 4. Install Python Dependencies

```bash
pip install -r requirements.txt
```

This will install PyMySQL and other required packages.

### 5. Initialize Database

```bash
python init_db.py
```

This creates all tables and sample data.

### 6. Setup Database Objects (Optional but Recommended)

```bash
python setup_database_objects.py
```

This creates stored procedures, functions, and triggers for enhanced functionality.

## Quick Start

1. **Install dependencies**: `pip install -r requirements.txt`
2. **Create MySQL database**: `CREATE DATABASE jrf_motorshop CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`
3. **Configure `.env` file**: Add MySQL connection details (see MySQL Database Setup above)
4. **Initialize database**: `python init_db.py`
5. **Setup database objects**: `python setup_database_objects.py` (optional but recommended)
6. **Run application**: `python app.py`
7. **Access**: Open http://localhost:5000 in your browser

## Default Login Credentials

After initializing the database, you can log in with:

- **Email**: `admin@jrfmotorcycle.com`
- **Password**: `admin123`

**Other test accounts:**
- Manager: `john.smith@jrfmotorcycle.com` / `password123`
- Staff: `sarah.johnson@jrfmotorcycle.com` / `password123`

## System Navigation

Once logged in, you'll have access to:

1. **Dashboard** (`/dashboard`) - Overview of system statistics
2. **Inventory** (`/inventory`) - Manage parts and stock
3. **Sales** (`/sales`) - Point-of-sale system
4. **Logout** - Secure logout

## Key Features Usage

### Inventory Management

1. **Add New Parts**: Click "Add Part" button, fill in the form, and save
2. **Edit Parts**: Click the edit icon (pencil) next to any part
3. **Delete Parts**: Click the delete icon (trash) next to any part
4. **Search/Filter**: Use the search bar and category filter to find parts
5. **Stock Monitoring**: Visual progress bars show stock levels (red=0, yellow=1-4, green=5+)

### Sales Management

1. **Add to Cart**: Click "Add to Cart" on any part
2. **Manage Cart**: Adjust quantities or remove items
3. **Payment Processing**: 
   - Click "Process Payment" when ready
   - Select payment method (Cash, Card, GCash, Bank Transfer)
   - For cash payments, enter amount received to calculate change
4. **Cart Persistence**: Cart items are saved in browser localStorage

## Database Schema

The system uses **MySQL database** with the following main tables:

- **staff** - User accounts and authentication
- **parts** - Inventory items and stock information
- **sales** - Sales transactions
- **sale_details** - Individual items in each sale
- **suppliers** - Supplier information
- **stock_entries** - Stock movement tracking
- **supplier_part** - Many-to-many relationship between suppliers and parts

**MySQL is required** - The system will not run without a MySQL connection configured.

## File Structure

```
jrf_system/
├── app.py              # Main Flask application
├── init_db.py          # Database initialization script
├── requirements.txt    # Python dependencies
├── templates/          # HTML templates
│   ├── base.html       # Base template
│   ├── base_new.html   # Updated base template
│   ├── dashboard.html  # Dashboard page
│   ├── inventory.html  # Inventory management
│   ├── sales.html      # Sales/POS system
│   └── login.html      # Login page
├── static/             # Static assets (CSS, JS, images)
└── .env                # Environment variables (MySQL credentials)
```

## Technologies Used

- **Backend**: Flask, SQLAlchemy, Flask-Login
- **Frontend**: Tailwind CSS, Font Awesome, JavaScript
- **Database**: MySQL (required)
- **Database Driver**: PyMySQL
- **Authentication**: Flask-Login with password hashing
