# here we writes all derived functions for azure


from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource import ResourceManagementClient


def available_zones(compute_client: ComputeManagementClient, region: str):
   
    # Get the list of SKUs available in the specified region
    zones = set()
    skus = compute_client.resource_skus.list()

    for sku in skus:
        # Filter SKUs by the specified region and availability zone support
        if region.lower() in [loc.location.lower() for loc in sku.locations]:
            if sku.location_info and sku.location_info[0].zones:
                zones.update(sku.location_info[0].zones)

    # Return sorted zones
    return sorted(zones)



def create_security_group(network_client: NetworkManagementClient, group_name: str, resource_group: str, region: str):
    
    ingress_rules = [
        {"protocol": "Tcp", "port": 22, "priority": 100},  # SSH
        {"protocol": "Tcp", "port": 80, "priority": 200},  # HTTP
        {"protocol": "Tcp", "port": 443, "priority": 300}  # HTTPS
    ]

    # Define NSG parameters
    nsg_params = {
        "location": region,
        "security_rules": []
    }

    # Add ingress rules if provided
    if ingress_rules:
        for rule in ingress_rules:
            nsg_params["security_rules"].append({
                "name": f"Allow-{rule['protocol']}-{rule['port']}",
                "protocol": rule["protocol"],
                "source_port_range": "*",
                "destination_port_range": str(rule["port"]),
                "source_address_prefix": "*",  # Adjust for specific source ranges if needed
                "destination_address_prefix": "*",
                "access": "Allow",
                "priority": rule["priority"],  # Priority must be unique and between 100-4096
                "direction": "Inbound"
            })

    # Create or update the Network Security Group
    nsg = network_client.network_security_groups.begin_create_or_update(
        resource_group_name=resource_group,
        network_security_group_name=group_name,
        parameters=nsg_params
    ).result()

    return nsg
