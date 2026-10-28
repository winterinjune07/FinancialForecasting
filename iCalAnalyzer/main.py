from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv
import iCalImport as iCal
import StringConvertor as StrConv
import csv
import os

load_dotenv()


##  Validating Environment Variables  ################################
payPeriodType = os.getenv("PAY_PERIOD_TYPE", "").strip().lower()
hourly = os.getenv("HOURLY_RATE", "").strip()
tips = os.getenv("AVG_TIPS", "").strip()
prevPayPeriod = StrConv.Date(os.getenv("PAST_PAY_PERIOD", "").strip())
dBetweenPPandPD = os.getenv("DAYS_BETWEEN_PAY_PERIOD_AND_PAYDAY", "").strip()

errors = []

if payPeriodType != 'daily' and payPeriodType != 'weekly' and payPeriodType != 'biweekly' and payPeriodType != 'monthly':
    errors.append('Invalid Pay Period')
if StrConv.Float(hourly) == False:
    errors.append('Invalid Hourly Rate')
if StrConv.Float(tips) == False:
    errors.append('Invalid Tips Rate')
if prevPayPeriod is None:
    errors.append('Invalid previous pay period')
if StrConv.Float(dBetweenPPandPD) == False:
    errors.append('Invalid Value for Days Between Pay Period and Payday')
if errors != []:
    print(f'Exitting program. Reasoning:\n {errors}')
######################################################################


# Variable confirmation #
hourly = float(hourly); tips = float(tips); dBetweenPPandPD = float(dBetweenPPandPD)


# CSV Template  :   uid, summary, start, end, location, description, status, last_modified
# Runs the pre-established calendar fetch service
iCal.main()


# Parse the file into a list of durations
trows = []
durations = []
dates = []

with open('./data/calendar.csv', 'r') as file:
    for line in file:
        for i in line.split(','):
            trows.append(i)
        if trows[5] != 'duration_minutes' and trows[5] != '':
            durations.append(float(trows[5]))
            a = trows[2].split('T')
            dates.append(a[0])
        trows = []

# Parse the pay period
today = date.today()

if payPeriodType == 'daily':
    daysToPay = 1
elif payPeriodType == 'weekly':
    daysToPay = 7
elif payPeriodType == 'biweekly':
    daysToPay = 14
else:
    daysToPay = 30


# Calculate the durations
StrConv.Float(hourly);  StrConv.Float(tips)
pay = float(hourly + tips)


# Consolidate the paychecks
periodLen = timedelta(days=daysToPay)
groups = {}  # payday -> list of durations

for dateStr, dur in zip(dates, durations):
    d = StrConv.Date(dateStr)
    n = -((prevPayPeriod - d) // periodLen)   # ceil: which payday closes this entry's period
    payday = prevPayPeriod + n * periodLen
    groups.setdefault(payday, []).append(dur)

sortedPayPeriods = [groups[p] for p in sorted(groups) if p <= today]
UpcomingCheckDurations = [dur for p in sorted(groups) if p > today for dur in groups[p]]


# Turning it into hours
consolidatedHours = []

for list in sortedPayPeriods:
    b = sum(list)
    consolidatedHours.append(b / 60)

c = sum(UpcomingCheckDurations)
consolidatedHours.append(c / 60)


# Convert to dollar amounts
grossPay = [i * float(pay) for i in consolidatedHours]


# Taxes
from LocalTaxLaws import breakdownMany

postTax = breakdownMany(grossPay)
netPay = [c['net'] for c in postTax['checks']]


# Turning it into a dictionary

output = []

for i in range(len(netPay)):
    # Pay Period Start
    PPS = ((prevPayPeriod - timedelta(days=daysToPay)) + timedelta(days=daysToPay) * StrConv.Int(i)) + timedelta(days=1)
    # Pay Period End
    PPE = (PPS + timedelta(days=daysToPay)) - timedelta(days=1)
    # Check Date
    CD = PPE + timedelta(days=dBetweenPPandPD)
    # Hours Worked
    H = consolidatedHours[i]
    # Gross Pay
    GP = grossPay[i]
    # Net Pay
    NP = netPay[i]

    # Making the data pretty
    PPS = PPS.strftime('%m-%d-%Y');     CD = CD.strftime('%m-%d-%Y');       PPE = PPE.strftime('%m-%d-%Y')
    H = StrConv.Float(H);               GP = StrConv.Float(GP);           NP = StrConv.Float(NP)

    d = {"Pay Period Start": PPS, "Pay Period End": PPE, "Check Date": CD, "Hours": H.__round__(3), "Gross Pay": GP.__round__(3), "Net Pay": NP.__round__(3)}
    output.append(d)

print('Results:')
for dict in output:
    print(f'\n {dict}')

path = Path(__file__).parent / 'data' / 'output-data.csv'
with open(path, 'w', newline='') as file:
    writer = csv.DictWriter(file, fieldnames=output[0].keys())
    writer.writeheader()
    writer.writerows(output)