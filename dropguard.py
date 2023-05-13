"""
Python script to automatically configure a DigitalOcean WireGuard VPN and retrieve its configuration.

WireGuard configuration based on: https://popovy.ch/blog/wireguard-vpn-server-with-ipv6-support-secure-dns-and-nftables
"""

import argparse
import json
import logging
import os
import re
import time

# External dependencies
import httpx
import paramiko
from scp import SCPClient


EXAMPLE = """Example usage:\n\n
List the available regions:
\tpython dropguard.py list --list-regions\n
Create a WireGuard VPN droplet with the name 'dropguard', adding SSH key with ID '12345678':
\tpython dropguard.py create --name dropguard --ssh-keys 12345678 --private-key ~/.ssh/your_private_key\n
Create a WireGuard VPN droplet with the name 'dropguard', adding SSH key with ID '12345678' in region Frankfurt:
\tpython dropguard.py create --name dropguard --ssh-keys 12345678 --private-key ~/.ssh/your_private_key --region fra1
"""


logging.basicConfig(format="%(asctime)s - %(message)s", level=logging.INFO)

# Set this as "Bearer DIGITALOCEAN_TOKEN"
try:
    TOKEN = os.environ["DO_TOKEN"]
except KeyError:
    logging.error("Please set your DigitalOcean token as an environment variable: `export DO_TOKEN=drop_v1_12345678`")
    exit(1)


HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

BASE_URL = "https://api.digitalocean.com"
REGIONS_URL = "/v2/regions"
IMAGES_URL = "/v2/images"
SSHKEYS_URL = "/v2/account/keys"
DROPLET_URL = "/v2/droplets"

DROPLET_CONFIGS = ["s-1vcpu-512mb-10gb", "s-1vcpu-1gb"]

FINISHED_PATTERN = re.compile("Cloud-init.+finished at")


class DigitalOceanError(Exception):
    pass


def request(url: str, data: dict = {}) -> dict:
    """Base function for performing requests.

    Args:
        url: The URI of the API endpoint.
        method: The HTTP method to use for the request.
        data: The data to sent with a POST request.

    Returns:
        The HTTP response as a `dict`.
    """

    with httpx.Client(headers=HEADERS) as client:
        if data:
            r = client.post(url, data=data)
        else:
            r = client.get(url)

        res = json.loads(r.text)

        if r.status_code != 200 and r.status_code != 202:
            raise DigitalOceanError(f"{res['id']} - {res['message']}")

    return res


def list_keys() -> None:
    """Basic function for listing the available SSH keys."""

    res = request(url=f"{BASE_URL}{SSHKEYS_URL}")

    for key in res["ssh_keys"]:
        logging.info(f"> {key['name']}")
        for field, info in key.items():
            if field != "name":
                print(f"\t{field}: {info}")


def list_images() -> None:
    """Basic function for listing the images that are available."""

    res = request(url=f"{BASE_URL}{IMAGES_URL}")

    logging.info(f"{res['meta']['total']} images available")
    for image in res["images"]:
        print(f"> {image['distribution']}")
        for field, info in image.items():
            if field != "distribution":
                print(f"\t{field}: {info}")


def list_regions() -> None:
    """Basic function for listing the regions and their information."""

    res = request(url=f"{BASE_URL}{REGIONS_URL}")

    for region in res["regions"]:
        if not region["available"]:
            continue

        logging.info(f"> {region['name']}")
        for field, info in region.items():
            if field != "name":
                print(f"\t{field}: {info}")


def config_status(ip: str, private_key: str, outfile: str) -> None:
    """Function to monitor the progress of the cloud-init script, retrieves the WireGuard configuration when the cloud-init is finished.

    Args:
        ip: The IP-address of the Droplet.
        outfile: The output filename to use for the WireGuard configuration.
    """

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    while True:
        # Monitor the cloud-init script status
        logging.info("waiting for cloud-init to finish")
        time.sleep(10)

        try:
            ssh_client.connect(hostname=ip, username="root", key_filename=private_key)
        except paramiko.ssh_exception.NoValidConnectionsError:
            # The SSH server takes a little while to start on the Droplet
            continue

        _, stdout, _ = ssh_client.exec_command("cat /var/log/cloud-init-output.log")

        if re.search(FINISHED_PATTERN, stdout.readlines()[-1]):
            # Check if the output indicates that the cloud-init script is finished (last line)
            # Save the WireGuard configuration file that was created by the cloud-init script
            logging.info("cloud-init finished, downloading WireGuard config")
            scp_client = SCPClient(ssh_client.get_transport())
            scp_client.get("/etc/wireguard/wg0-client.conf", outfile)
            logging.info(f"configuration saved at {outfile}")
            break

    ssh_client.close()


def droplet_status(droplet_id: str) -> dict:
    """Function to check droplet status after creation.

    Args:
        droplet_id: The ID that was given to the droplet upon creation.
    """

    while True:
        time.sleep(5)
        res = request(url=f"{BASE_URL}{DROPLET_URL}/{droplet_id}")
        if res["droplet"]["status"] == "active":
            return res["droplet"]


def create_droplet(port: str, name: str, region: str, size: str, ssh_keys: list, private_key: str, output: str) -> None:
    """Create the droplet with the given information.

    Args:
        port: The WireGuard port to configure.
        name: The name of the droplet.
        region: The region to use for the droplet.
        size: Specifications of the machine.
        ssh_key: The SSH key to configure on the droplet.
        output: The output filename to use for the WireGuard configuration.

    Returns:
        The droplet configuration that was just created as a `dict`.
    """

    logging.info(f"setting cloud_config.yml")

    with open("cloud_config.yml", "r") as config_fh:
        user_data = config_fh.read()

    user_data = user_data.replace("WG_PORT", port)

    request_data = {
        "name": name,
        "region": region,
        "size": size,
        "image": "debian-11-x64",
        "ssh_keys": ssh_keys,
        "tags": [
            "DROPGUARD",
        ],
        "user_data": user_data,
    }

    res = request(url=f"{BASE_URL}{DROPLET_URL}", data=json.dumps(request_data))

    logging.info("waiting for droplet to become active")
    try:
        droplet_data = droplet_status(droplet_id=res["droplet"]["id"])
    except KeyError:
        logging.error(f"failed to check droplet status")
        return

    for ipaddr in droplet_data["networks"]["v4"]:
        if ipaddr["type"] == "public":
            droplet_ip = ipaddr["ip_address"]
            logging.info(f"droplet is active: {droplet_ip}")
            break

    logging.info("checking cloud-config status")
    config_status(ip=droplet_ip, private_key=private_key, outfile=output)


def main(args):
    if args.action == "list":
        try:
            if args.list_regions:
                list_regions()
            elif args.list_images:
                list_images()
            elif args.list_keys:
                list_keys()
            else:
                logging.error("please pick a valid --list command or use 'list --help'")
                exit(1)
        except DigitalOceanError as e:
            logging.error(e)
            exit(1)
    else:
        logging.info("creating droplet")
        try:
            create_droplet(
                port=args.port,
                name=args.name,
                region=args.region,
                size=args.size,
                ssh_keys=args.ssh_keys,
                private_key=args.private_key,
                output=args.output,
            )

        except DigitalOceanError as e:
            logging.error(e)
            exit(1)


if __name__ == "__main__":
    if not TOKEN:
        logging.error("please set the `TOKEN` variable with the DigitalOcean authentication token")
        exit(1)

    parser = argparse.ArgumentParser(
        description="Python script to automate the DigitalOcean Droplet WireGuard configuration.",
        epilog=EXAMPLE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(title="available options", dest="action")

    listparser = subparsers.add_parser("list")
    listparser.add_argument("-lr", "--list-regions", action="store_true", required=False, help="List available regions")
    listparser.add_argument("-li", "--list-images", action="store_true", required=False, help="List available images")
    listparser.add_argument("-lk", "--list-keys", action="store_true", required=False, help="List available SSH keys")

    createparser = subparsers.add_parser("create")
    createparser.add_argument(
        "-r",
        "--region",
        required=False,
        default="fra1",
        help="Region to create the droplet in [default: Frankfurt 1 (fra1)]",
    )
    createparser.add_argument("-n", "--name", required=True, help="Droplet name")
    createparser.add_argument(
        "-s",
        "--size",
        required=False,
        default="s-1vcpu-512mb-10gb",
        help="Size of the droplet to create [default: s-1vcpu-512mb-10gb]",
    )
    createparser.add_argument(
        "-k",
        "--ssh-keys",
        required=True,
        nargs="+",
        help="Add SSH key(s) present in the DigitalOcean account store (ID or thumbprint)",
    )
    createparser.add_argument(
        "-pk",
        "--private-key",
        required=True,
        help="SSH private key to use when authenticating to Droplet",
    )
    createparser.add_argument(
        "-p", "--port", required=False, default="42069", help="Port to use for WireGuard [default: 42069]"
    )
    createparser.add_argument(
        "-o",
        "--output",
        required=False,
        default="dropguard.conf",
        help="Filename to save WireGuard config to [default: dropguard.conf]",
    )

    args = parser.parse_args()

    main(args)
