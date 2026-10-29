from iCalAnalyzer.MainAnalyzer import MainAnalyzer
import Components.RecurringBillsInputs as RecurringBillsInputs
from pathlib import Path
import os

workDir = Path(__file__).resolve().parent  # Get the Working Directory

### This is the main entry point, and the part that uses the iCal-Analyzer Repository.
### Main Analyzer first tells the Importer program to pull the iCal data from the API, and the imported data is then parsed into data/calendar.csv
### Then, the Main Analyzer reads the calendar file and calculates the Pay Periods, Check Dates, Hours per period, and Gross Pay and puts it into data/output-data.csv
### It then hands it off to LocalTaxLaws, who takes the output-data.csv, and calculates the net pay based on local tax laws, and forecasts the net pay.

MainAnalyzer()

# This is the part that takes all the recurring expenses inputs.

# Print current logged recurring expenses

if os.path.exists(f'{workDir}/data/bills.csv'):
    with open(f'{workDir}/data/bills.csv', mode='r') as file:
        print("Current logged recurring expenses:\n")
        for line in file:
            currentBills = '\t'.join(line.strip().split(','))
            print(f'{currentBills}\n')

# Sees if the you want to add more recurring bills, and if so, calls the RecurringBillsInputs module to add them.
more_bills = ''
while more_bills not in ['yes', 'no']:
    more_bills = input("Do you want to add recurring bills? (yes/no): ").strip().lower()
if more_bills == 'yes':
    RecurringBillsInputs.main()
print('Done!')