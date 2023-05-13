# DROPGUARD

Small Python script to automatically deploy a WireGuard VPN

## Description

This script creates a new `DigitalOcean` Droplet, sets up the VPS and installs `WireGuard`. While the VPS is being configured it will use `paramiko` to check the status of the configuration and retrieve the `WireGuard` configuration file.

Store the `WireGuard` configuration file in a safe location and import the configuration using the `WireGuard` application.

Most of the `WireGuard` configuration steps were taken from: https://popovy.ch/blog/wireguard-vpn-server-with-ipv6-support-secure-dns-and-nftables

## Prerequisites

Install the following Python packages before running the script:

```sh
pip install httpx paramiko scp
```

Add the DigitalOcean token to your environment variables:

```sh
export DO_TOKEN=drop_v1_12345678
```

## Usage

List the available commands for listing regions, images and SSH keys:

```sh
python3 dropguard.py list --help                                                                                                                                     [0:34:19]
usage: dropguard.py list [-h] [-lr] [-li] [-lk]

options:
  -h, --help           show this help message and exit
  -lr, --list-regions  List available regions
  -li, --list-images   List available images
  -lk, --list-keys     List available SSH keys
```

List the available commands for creating a new `DigitalOcean` Droplet and `WireGuard` VPN:

```sh
$ python dropguard.py create --help                                                                                                       [13:03:47]
usage: dropguard.py create [-h] [-r REGION] -n NAME [-s SIZE] -k SSH_KEYS [SSH_KEYS ...] -pk PRIVATE_KEY [-p PORT] [-o OUTPUT]

options:
  -h, --help            show this help message and exit
  -r REGION, --region REGION
                        Region to create the droplet in [default: Frankfurt 1 (fra1)]
  -n NAME, --name NAME  Droplet name
  -s SIZE, --size SIZE  Size of the droplet to create [default: s-1vcpu-512mb-10gb]
  -k SSH_KEYS [SSH_KEYS ...], --ssh-keys SSH_KEYS [SSH_KEYS ...]
                        Add SSH key(s) present in the DigitalOcean account store (ID or thumbprint)
  -pk PRIVATE_KEY, --private-key PRIVATE_KEY
                        SSH private key to use when authenticating to Droplet
  -p PORT, --port PORT  Port to use for WireGuard [default: 42069]
  -o OUTPUT, --output OUTPUT
                        Filename to save WireGuard config to [default: dropguard.conf]
```

Example usage:

```sh
# List the available regions:
        python dropguard.py list --list-regions

# Create a WireGuard VPN droplet with the name 'dropguard', adding SSH key with ID '12345678':
        python dropguard.py create --name dropguard --ssh-keys 12345678

# Create a WireGuard VPN droplet with the name 'dropguard', adding SSH key with ID '12345678' in region Frankfurt:
        python dropguard.py create --name dropguard --ssh-keys 12345678 --private-key ~/.ssh/your_private_key --region fra1
```
