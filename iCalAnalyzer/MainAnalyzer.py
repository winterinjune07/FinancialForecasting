def MainAnalyzer():
    from datetime import date, timedelta
    from . import StringConvertor as StrConv
    from dotenv import load_dotenv
    from . import Importer as iCal
    from pathlib import Path
    import sys
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
        sys.exit(1)
    ######################################################################


    # Variable confirmation #
    hourly = float(hourly); tips = float(tips); dBetweenPPandPD = float(dBetweenPPandPD)


    # Runs the pre-established calendar fetch service. It writes
    #   data/calendar.csv    - every raw event
    #   data/pay_periods.csv - hours worked per pay period. Only "Panera" shifts
    #                          count, and time on a scheduled day off is excluded.
    iCal.main()


    # Read the hours per pay period
    today = date.today()
    pay = hourly + tips

    periodsPath = Path(__file__).parent.parent / 'data' / 'pay_periods.csv'
    periods = []
    periodsPathParent = periodsPath.parent
    periodsPathParent.mkdir(parents=True, exist_ok=True)
    if not os.path.exists(periodsPath):
        os.mknod(periodsPath)  # Create the file if it doesn't exist

    with open(periodsPath, 'r', newline='', encoding='utf-8') as file:
        for r in csv.DictReader(file):
            periods.append({
                'start': date.fromisoformat(r['period_start']),
                'end': date.fromisoformat(r['period_end']),
                'hours': float(r['hours_worked']),
            })

    periods.sort(key=lambda p: p['start'])


    # Which periods get a row: every period that has ended, the one in progress,
    # and any later period that already has shifts scheduled (no gaps in between).
    current = next((i for i, p in enumerate(periods) if p['end'] > today), len(periods) - 1)
    last = max([current] + [i for i, p in enumerate(periods) if p['hours'] > 0])
    periods = periods[:last + 1]

    consolidatedHours = [p['hours'] for p in periods]


    # Convert to dollar amounts
    grossPay = [i * pay for i in consolidatedHours]


    # Taxes
    from .LocalTaxLaws import breakdownMany

    postTax = breakdownMany(grossPay)
    netPay = [c['net'] for c in postTax['checks']]


    # Turning it into a dictionary

    output = []

    for i, p in enumerate(periods):
        # Pay Period Start / End
        PPS = p['start']
        PPE = p['end']
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

    path = Path(__file__).parent.parent / 'data' / 'output-data.csv'
    with open(path, 'w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=output[0].keys())
        writer.writeheader()
        writer.writerows(output)