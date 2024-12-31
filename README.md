# ASA to FMC Route Migrator

This tool facilitates the migration of route configurations from Cisco ASA (Adaptive Security Appliance) to FMC (Firepower Management Center). It helps network administrators automate the process of converting route configurations when transitioning from ASA to Firepower Threat Defense (FTD) managed by FMC.

## Features

- Converts ASA route configurations to FMC-compatible format
- Supports static routes migration
- Maintains routing parameters and metrics
- Preserves network addressing and subnet information

## Requirements

- Python 3.x
- ASA configuration file with route entries

## Usage

1. Prepare your ASA configuration file
2. Run the script:
   ```bash
   python asaToFMCrouteMigrator.py
   ```
3. Follow the prompts to specify input and output files

## Input Format

The script expects ASA configuration files containing route entries in the standard ASA syntax.

## Output

The script generates FMC-compatible route configurations that can be imported into your FMC deployment.

## Notes

- Always verify the converted routes before deploying to production
- Back up your configurations before making any changes
- Test the converted routes in a non-production environment first