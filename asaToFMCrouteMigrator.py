#!/usr/bin/env python3
import requests
import json
import sys
import time
from typing import List, Dict, Set
from collections import defaultdict
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class FMCRouteConverter:
    def __init__(self, fmc_host: str, username: str, password: str):
        self.fmc_host = fmc_host
        self.username = username
        self.password = password
        self.headers = None
        self.domain_uuid = None
        self.device_id = None
        
        # Cache for network/host objects
        self.network_objects = {}
        self.host_objects = {}

    def login(self) -> None:
        """Authenticate to FMC and get access token"""
        auth_url = f"https://{self.fmc_host}/api/fmc_platform/v1/auth/generatetoken"
        try:
            response = requests.post(
                auth_url,
                auth=(self.username, self.password),
                verify=False
            )
            response.raise_for_status()
            self.headers = {
                'X-auth-access-token': response.headers.get('X-auth-access-token'),
                'Content-Type': 'application/json'
            }
            self.domain_uuid = response.headers.get('DOMAIN_UUID')
        except requests.exceptions.RequestException as e:
            print(f"Error authenticating to FMC: {e}")
            sys.exit(1)

    def get_device_id(self, device_name: str) -> None:
        """Get the device ID for the specified FTD device"""
        url = f"https://{self.fmc_host}/api/fmc_config/v1/domain/{self.domain_uuid}/devices/devicerecords"
        try:
            response = requests.get(url, headers=self.headers, verify=False)
            response.raise_for_status()
            devices = response.json().get('items', [])
            for device in devices:
                if device['name'] == device_name:
                    self.device_id = device['id']
                    return
            print(f"Device {device_name} not found")
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"Error getting device ID: {e}")
            sys.exit(1)

    def get_existing_objects(self) -> None:
        """Get existing network/host objects from FMC"""
        print("Fetching existing network objects...")
        
        # Get network objects
        url = f"https://{self.fmc_host}/api/fmc_config/v1/domain/{self.domain_uuid}/object/networks?limit=1000"
        try:
            response = requests.get(url, headers=self.headers, verify=False)
            response.raise_for_status()
            for obj in response.json().get('items', []):
                if 'name' in obj:
                    key = f"{obj['name']}"
                    self.network_objects[key] = obj
                    print(f"Found network object: {obj['name']}")
        except requests.exceptions.RequestException as e:
            print(f"Error getting network objects: {e}")

        print("\nFetching existing host objects...")
        
        # Get host objects
        url = f"https://{self.fmc_host}/api/fmc_config/v1/domain/{self.domain_uuid}/object/hosts?limit=1000"
        try:
            response = requests.get(url, headers=self.headers, verify=False)
            response.raise_for_status()
            for obj in response.json().get('items', []):
                if 'name' in obj:
                    self.host_objects[obj['name']] = obj
                    print(f"Found host object: {obj['name']}")
        except requests.exceptions.RequestException as e:
            print(f"Error getting host objects: {e}")
            
        print(f"\nTotal objects found: {len(self.network_objects)} networks, {len(self.host_objects)} hosts")

    def find_or_create_object(self, value: str, mask: str = None) -> Dict:
        """Find existing object by value/mask or return None"""
        is_host = mask == '255.255.255.255' or mask is None
        
        # Determine which cache to use
        cache = self.host_objects if is_host else self.network_objects
        cache_key = "obj-" + value if is_host else ("obj-" + value)
        
        # Look for existing object
        if cache_key in cache:
            print(f"Found existing object: {cache[cache_key]['name']} for {value}")
            return cache[cache_key]
        
        print(f"Warning: No existing object found for {value}")
        return None

    def parse_and_prepare_routes(self, filename: str) -> List[Dict]:
        """Parse ASA routes and prepare FMC route objects"""
        routes = []
        missing_objects = set()
        
        print("\nParsing routes and matching objects...")
        with open(filename, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 6 and parts[0] == 'route':
                    interface = parts[1]
                    network = parts[2]
                    netmask = parts[3]
                    gateway = parts[4]
                    metric = int(parts[5])

                    # Find gateway object
                    gw_obj = self.find_or_create_object(gateway)
                    if not gw_obj:
                        missing_objects.add(f"Gateway: {gateway}")
                        continue
                    
                    # Find network object
                    net_obj = self.find_or_create_object(network, netmask)
                    if not net_obj:
                        missing_objects.add(f"Network: {network}/{netmask}")
                        continue

                    # Create route object
                    route = {
                        "interfaceName": interface,
                        "selectedNetworks": [{
                            "type": net_obj['type'],
                            "id": net_obj['id'],
                            "name": net_obj['name']
                        }],
                        "gateway": {
                            "object": {
                                "type": gw_obj['type'],
                                "id": gw_obj['id'],
                                "name": gw_obj['name']
                            }
                        },
                        "metricValue": metric,
                        "type": "IPv4StaticRoute",
                        "isTunneled": False
                    }
                    routes.append(route)
                    print(f"Prepared route: {network}/{netmask} via {gateway}")

        if missing_objects:
            print("\nWARNING: The following objects were not found in FMC:")
            for obj in sorted(missing_objects):
                print(f"  - {obj}")
            print("\nPlease create these objects in FMC before proceeding.")
            sys.exit(1)

        return routes

    def deploy_routes(self, routes: List[Dict]) -> None:
        """Deploy routes to FTD via FMC API"""
        url = f"https://{self.fmc_host}/api/fmc_config/v1/domain/{self.domain_uuid}/devices/devicerecords/{self.device_id}/routing/ipv4staticroutes"
        
        total = len(routes)
        print(f"\nDeploying {total} routes...")
        
        for i, route in enumerate(routes, 1):
            try:
                response = requests.post(url, headers=self.headers, json=route, verify=False)
                response.raise_for_status()
                print(f"[{i}/{total}] Successfully deployed route to {route['selectedNetworks'][0]['name']}")
                
                # Add small delay every 10 routes to avoid overwhelming the API
                if i % 10 == 0:
                    time.sleep(1)
                    
            except requests.exceptions.RequestException as e:
                print(f"Error deploying route to {route['selectedNetworks'][0]['name']}: {e}")
                print(f"Failed route details: {json.dumps(route, indent=2)}")
                print("\nStopping deployment due to error.")
                sys.exit(1)

def main():
    # Configuration parameters
    FMC_HOST = "fmc_ip_addr"  # Replace with actual FMC hostname/IP
    USERNAME = "username"  # Replace with actual username
    PASSWORD = "password"  # Replace with actual password
    DEVICE_NAME = "FTD_NAME"  # Replace with FTD device name as shown in FMC
    ROUTES_FILE = "asa-routes.txt"  # Replace with actual file path

    # Initialize FMC API client
    fmc = FMCRouteConverter(FMC_HOST, USERNAME, PASSWORD)
    
    # Login to FMC
    print("Logging in to FMC...")
    fmc.login()
    
    # Get device ID
    print(f"Getting device ID for {DEVICE_NAME}...")
    fmc.get_device_id(DEVICE_NAME)
    
    # Get existing objects
    print("Getting existing network objects...")
    fmc.get_existing_objects()
    
    # Parse routes and prepare them
    print("Parsing and preparing routes...")
    routes = fmc.parse_and_prepare_routes(ROUTES_FILE)
    
    # Confirm deployment
    print(f"\nReady to deploy {len(routes)} routes.")
    confirm = input("Do you want to proceed? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Deployment cancelled.")
        sys.exit(0)
    
    # Deploy routes
    fmc.deploy_routes(routes)
    
    print("\nRoute deployment complete!")

if __name__ == "__main__":
    main()