#!/bin/bash

echo "🚀 Initializing AutoMark SVN Server..."

# Create main SVN repository structure
if [ ! -d "/var/svn/repositories/automark" ]; then
    echo "📁 Creating main SVN repository..."
    svnadmin create /var/svn/repositories/automark
    
    # Set permissions
    chown -R www-data:www-data /var/svn/repositories/automark
    
    echo "✅ SVN repository created at /var/svn/repositories/automark"
fi

# Create initial repository structure
if [ ! -f "/var/svn/repositories/automark/.initialized" ]; then
    echo "📋 Creating initial repository structure..."
    
    # Create temporary working directory
    TEMP_WC="/tmp/svn-init"
    rm -rf $TEMP_WC
    mkdir -p $TEMP_WC
    
    # Checkout empty repository
    svn checkout file:///var/svn/repositories/automark $TEMP_WC
    
    cd $TEMP_WC
    
    # Create base directory structure (templates will be created dynamically via API)
    mkdir -p templates
    mkdir -p student-repos
    
    # Create README for the repository
    cat > README.md << 'EOF'
# AutoMark SVN Repository

This repository contains:

## Templates Directory
- Assignment templates created by lecturers
- Students checkout templates to start assignments
- Format: templates/YEAR-SEMESTER-SUBJECT-AssignmentN/

## Student Repos Directory  
- Student submission repositories
- Organized by student and assignment
- Used for collecting student work

## Usage

### For Students:
```bash
# Checkout assignment template
svn checkout svn://automark-svn/templates/2025-AUT-Comp0067-Assignment1 .

# Work on assignment, then submit
svn add .
svn commit -m "Assignment submission"
```

### For Lecturers:
- Create assignment templates via the AutoMark web interface
- Templates are automatically added to this repository
- View student submissions through the web dashboard
EOF

    # Add all files to SVN
    svn add *
    
    # Commit initial structure
    svn commit -m "Initial assignment templates structure" --username admin --password adminpass123 --no-auth-cache
    
    # Mark as initialized
    touch /var/svn/repositories/automark/.initialized
    
    # Cleanup
    cd /
    rm -rf $TEMP_WC
    
    echo "✅ Initial repository structure created"
fi

echo "🔧 Setting up SVN server configuration..."

# Start SVN server
echo "🚀 Starting SVN server on port 3690..."
exec svnserve --daemon --foreground --listen-port 3690 --listen-host 0.0.0.0 \
    --root /var/svn/repositories --config-file /etc/subversion/svnserve.conf
