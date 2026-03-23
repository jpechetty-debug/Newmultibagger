import pandas_market_calendars as mcal
from datetime import datetime

def check_calendar():
    print("--- Sovereign AI Calendar Verifier ---")
    current_year = datetime.now().year
    
    try:
        nse = mcal.get_calendar('NSE')
        schedule = nse.schedule(start_date=f'{current_year}-01-01', end_date=f'{current_year}-12-31')
        
        trading_days = len(schedule)
        print(f"✅ Successfully loaded NSE calendar for {current_year}.")
        print(f"✅ Total Trading Days: {trading_days}")
        
        # Determine holidays loosely by comparing all weekdays to schedule
        import pandas as pd
        all_weekdays = pd.bdate_range(start=f'{current_year}-01-01', end=f'{current_year}-12-31').date
        trading_dates = set(schedule.index.date)
        holidays = [d for d in all_weekdays if d not in trading_dates]
        
        print(f"✅ Identified {len(holidays)} weekday holidays.")
        print("\nUpcoming Holidays (Next 5):")
        
        today = datetime.now().date()
        future_holidays = [h for h in holidays if h >= today][:5]
        
        for h in future_holidays:
            print(f"  - {h.strftime('%Y-%m-%d')} ({h.strftime('%A')})")
            
        print("\nStatus: HEALTHY")
        
    except Exception as e:
        print(f"❌ Failed to load calendar data: {e}")
        
if __name__ == "__main__":
    check_calendar()
