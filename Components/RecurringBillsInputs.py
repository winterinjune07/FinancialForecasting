def main():
    """
    Function to get user inputs for recurring bills and save them to a CSV file.
    """
    import csv
    import os
    from pathlib import Path
    import iCalAnalyzer.StringConvertor as sc

    dir = Path(__file__).resolve().parent.parent  # Get the parent directory of the current file

    # Reads previously saved bills
    def readBills(file_path):
        bills = []
        with open(file_path, mode='r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                bills.append(row)
        return bills

    # Writes the bills to a CSV file
    def writeBills(file_path, bills):
        with open(file_path, mode='w', newline='') as file:
            fieldnames = bills[0].keys() if bills else []
            csv_writer = csv.DictWriter(file, fieldnames=fieldnames)
            csv_writer.writeheader()
            for bill in bills:
                csv_writer.writerow(bill)

    # Initialization
    more_bills = ""
    counter = 0
    bill_amount = ""
    bill_due_date = ""

    p = dir / 'data'
    p.mkdir(parents=True, exist_ok=True)  # Create the 'data' directory

    if not os.path.exists(f'{dir}/data/bills.csv'):
        os.mknod(f'{dir}/data/bills.csv')  # Create the file if it doesn't exist

    while more_bills != 'no':
        # Get user input for bill details
        bill_name = input("Enter the name of the bill: ")
        while sc.Float(bill_amount ) is False:
            bill_amount = input("Enter the dollar amount of the bill: ")
            if counter > 0 and sc.Float(bill_amount) is False:
                print("Please enter a valid number for the bill amount.")
            counter += 1
        while sc.Int(bill_due_date) is False:
            if counter > 0 and sc.Int(bill_due_date) is False:
                print("Please enter a valid numerical day of the month for the bill due date.")
            bill_due_date = input("Enter the day of the month when the bill is due: ")
            counter += 1

        # Create a dictionary for the new bill
        new_bill = {
            'Name': bill_name,
            'Amount': bill_amount,
            'Day of Month': bill_due_date
        }

        # Read existing bills from file
        bills = readBills(f'{dir}/data/bills.csv')

        # Append the new bill to the list
        bills.append(new_bill)

        # Write updated bills back to file
        writeBills(f'{dir}/data/bills.csv', bills)

        # Ask if the user wants to add more 
        more_bills = input("Do you want to add another bill? (yes/no): ").strip().lower()
        while more_bills not in ['yes', 'no']:
            more_bills = input("Invalid Answer. Do you want to add another bill? (yes/no): ").strip().lower()