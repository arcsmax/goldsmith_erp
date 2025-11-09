#!/bin/bash
# Podman Installation and Setup Script for Goldsmith ERP
# Supports: Ubuntu 22.04+, Debian 12+, Fedora 38+, RHEL 9+

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Goldsmith ERP - Podman Installation  ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    VERSION=$VERSION_ID
else
    echo -e "${RED}✗ Cannot detect OS. /etc/os-release not found.${NC}"
    exit 1
fi

echo -e "${YELLOW}📋 Detected OS: $OS $VERSION${NC}"
echo ""

# Function to install Podman on Ubuntu/Debian
install_podman_debian() {
    echo -e "${YELLOW}📦 Installing Podman on Debian/Ubuntu...${NC}"

    sudo apt-get update
    sudo apt-get install -y \
        podman \
        podman-compose \
        buildah \
        skopeo \
        fuse-overlayfs \
        slirp4netns

    echo -e "${GREEN}✓ Podman installed${NC}"
}

# Function to install Podman on Fedora/RHEL
install_podman_fedora() {
    echo -e "${YELLOW}📦 Installing Podman on Fedora/RHEL...${NC}"

    sudo dnf install -y \
        podman \
        podman-compose \
        buildah \
        skopeo

    echo -e "${GREEN}✓ Podman installed${NC}"
}

# Install Podman based on OS
case $OS in
    ubuntu|debian)
        install_podman_debian
        ;;
    fedora|rhel|centos)
        install_podman_fedora
        ;;
    *)
        echo -e "${RED}✗ Unsupported OS: $OS${NC}"
        echo -e "${YELLOW}Please install Podman manually:${NC}"
        echo "  https://podman.io/docs/installation"
        exit 1
        ;;
esac

# Verify installation
echo ""
echo -e "${YELLOW}🔍 Verifying installation...${NC}"
podman --version
echo -e "${GREEN}✓ Podman version confirmed${NC}"

# Configure rootless Podman
echo ""
echo -e "${YELLOW}⚙️  Configuring rootless Podman...${NC}"

# Create systemd user directory if it doesn't exist
mkdir -p ~/.config/systemd/user

# Enable lingering (allows rootless containers to run at boot)
if command -v loginctl &> /dev/null; then
    loginctl enable-linger $USER
    echo -e "${GREEN}✓ User lingering enabled${NC}"
fi

# Configure subuid/subgid for rootless mode
if ! grep -q "^$USER:" /etc/subuid 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Configuring user namespaces...${NC}"
    echo -e "${YELLOW}   This requires sudo access.${NC}"

    # Add subuid/subgid entries
    echo "$USER:100000:65536" | sudo tee -a /etc/subuid
    echo "$USER:100000:65536" | sudo tee -a /etc/subgid

    # Restart user namespace
    podman system migrate
    echo -e "${GREEN}✓ User namespaces configured${NC}"
fi

# Create Podman configuration directory
mkdir -p ~/.config/containers

# Configure storage for rootless
cat > ~/.config/containers/storage.conf <<EOF
# Podman storage configuration for rootless mode
[storage]
driver = "overlay"

[storage.options]
mount_program = "/usr/bin/fuse-overlayfs"

[storage.options.overlay]
mountopt = "nodev,metacopy=on"
EOF

echo -e "${GREEN}✓ Storage configuration created${NC}"

# Setup Goldsmith ERP
echo ""
echo -e "${YELLOW}🚀 Setting up Goldsmith ERP...${NC}"

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${GREEN}✓ .env file created from .env.example${NC}"

        # Generate secure SECRET_KEY
        SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
        sed -i "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
        echo -e "${GREEN}✓ Secure SECRET_KEY generated${NC}"
    else
        echo -e "${YELLOW}⚠️  .env.example not found. Skipping .env creation.${NC}"
    fi
else
    echo -e "${GREEN}✓ .env file already exists${NC}"
fi

# Create alias for docker -> podman
echo ""
echo -e "${YELLOW}🔧 Creating Docker compatibility aliases...${NC}"

SHELL_RC=""
if [ -n "$BASH_VERSION" ]; then
    SHELL_RC="$HOME/.bashrc"
elif [ -n "$ZSH_VERSION" ]; then
    SHELL_RC="$HOME/.zshrc"
fi

if [ -n "$SHELL_RC" ]; then
    if ! grep -q "alias docker=podman" "$SHELL_RC" 2>/dev/null; then
        cat >> "$SHELL_RC" <<EOF

# Goldsmith ERP - Podman aliases
alias docker=podman
alias docker-compose=podman-compose
EOF
        echo -e "${GREEN}✓ Aliases added to $SHELL_RC${NC}"
        echo -e "${YELLOW}   Run: source $SHELL_RC${NC}"
    else
        echo -e "${GREEN}✓ Aliases already exist${NC}"
    fi
fi

# Build and start containers
echo ""
echo -e "${YELLOW}🏗️  Building containers...${NC}"
podman-compose -f podman-compose.yml build

echo ""
echo -e "${YELLOW}🚀 Starting services...${NC}"
podman-compose -f podman-compose.yml up -d

# Wait for services to be healthy
echo ""
echo -e "${YELLOW}⏳ Waiting for services to be ready...${NC}"
sleep 10

# Check service status
echo ""
echo -e "${YELLOW}📊 Service Status:${NC}"
podman-compose -f podman-compose.yml ps

# Final instructions
echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Installation Complete! 🎉         ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}✓ Goldsmith ERP is now running in rootless Podman!${NC}"
echo ""
echo -e "${YELLOW}📍 Access points:${NC}"
echo "   Backend API:     http://localhost:8000"
echo "   API Docs:        http://localhost:8000/docs"
echo "   Frontend:        http://localhost:3000"
echo ""
echo -e "${YELLOW}🛠️  Useful commands:${NC}"
echo "   View logs:       podman-compose -f podman-compose.yml logs -f"
echo "   Stop services:   podman-compose -f podman-compose.yml down"
echo "   Restart:         podman-compose -f podman-compose.yml restart"
echo "   Status:          podman-compose -f podman-compose.yml ps"
echo ""
echo -e "${YELLOW}🔐 Security improvements with Podman:${NC}"
echo "   ✓ Rootless containers (no daemon)"
echo "   ✓ No elevated privileges required"
echo "   ✓ User namespace isolation"
echo "   ✓ SELinux/AppArmor compatible"
echo ""
echo -e "${YELLOW}💡 Next steps:${NC}"
echo "   1. Review .env file for security settings"
echo "   2. Change default passwords in .env"
echo "   3. Run: podman-compose logs -f"
echo ""
echo -e "${GREEN}Happy coding! 🚀${NC}"
