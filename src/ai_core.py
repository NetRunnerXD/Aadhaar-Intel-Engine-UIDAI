import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
import datetime

class AnalyticsEngine:
    def __init__(self, df_enrol, df_demo, df_bio):
        self.df_enrol = df_enrol
        self.df_demo = df_demo
        self.df_bio = df_bio

    def get_market_share(self):
        if self.df_enrol.empty: return pd.DataFrame()
        return self.df_enrol.groupby(['state', 'district'])['adult_enrolments'].sum().reset_index()

    def get_correlation(self):
        if self.df_enrol.empty: return pd.DataFrame()
        e = self.df_enrol.groupby('district')['adult_enrolments'].sum()
        b = self.df_bio.groupby('district')['bio_stress'].sum() if not self.df_bio.empty else pd.Series(dtype='float64')
        merged = pd.concat([e, b], axis=1).fillna(0)
        merged.columns = ['Enrolments', 'Bio_Updates']
        return merged.reset_index().rename(columns={'index': 'district'})

    def get_anomalies(self):
        df = self.get_market_share()
        if len(df) < 10: 
            df['risk_score'] = 0
            return df
            
        iso = IsolationForest(contamination=0.05, random_state=42)
        df['anomaly'] = iso.fit_predict(df[['adult_enrolments']])
        
        max_val = df['adult_enrolments'].max()
        df['risk_score'] = np.where(
            df['anomaly'] == -1, 
            (df['adult_enrolments'] / (max_val if max_val > 0 else 1) * 90) + 10, 
            0
        ).astype(int)
        
        return df[df['risk_score'] > 0].sort_values('risk_score', ascending=False)

    def forecast_trends(self, horizon=30, growth_factor=0.0, model_type="Linear"):
        if self.df_enrol.empty: return None, "No Data"
        
        if not pd.api.types.is_datetime64_any_dtype(self.df_enrol['date']):
            self.df_enrol['date'] = pd.to_datetime(self.df_enrol['date'])
        
        daily = self.df_enrol.groupby('date')['adult_enrolments'].sum().sort_index().reset_index()
        if daily.empty: return None, "No Data"

        last_known_date = daily['date'].max()
        start_val = daily.iloc[-1]['adult_enrolments']
        
        if start_val < 10 and len(daily) > 1:
            start_val = daily.iloc[-2]['adult_enrolments']

        volatility = 0.05
        if len(daily) > 5:
            std_dev = daily['adult_enrolments'].pct_change().std()
            if not np.isnan(std_dev) and std_dev > 0:
                volatility = std_dev
            
        drift = 0.002 if model_type == "Linear" else 0.005
        current_val = start_val
        preds = []

        for _ in range(horizon):
            shock = np.random.normal(loc=drift, scale=volatility)
            current_val *= (1 + shock)
            current_val *= (1 + (growth_factor / horizon))
            preds.append(max(0, current_val))

        future_dates = [last_known_date + datetime.timedelta(days=i) for i in range(1, horizon+1)]
        sim_preds = np.array(preds)
        
        return pd.DataFrame({
            'date': future_dates, 
            'predicted': sim_preds,
            'upper': sim_preds * 1.2,
            'lower': sim_preds * 0.8
        }), "Stochastic"

    def generate_forecast_insight(self, forecast_df, model_type):
        if forecast_df is None or forecast_df.empty: return "Insufficient data for insight."
            
        change_pct = ((forecast_df.iloc[-1]['predicted'] / forecast_df.iloc[0]['predicted']) - 1) * 100
        direction = "Growth" if change_pct > 0 else "Decline"
        emoji = "📈" if change_pct > 0 else "📉"
        
        msg = f"**{emoji} Projection:** The {model_type} stochastic model predicts a **{abs(change_pct):.1f}% {direction}**."
        
        if abs(change_pct) > 10:
            msg += "\n\n **Action Required:** Significant volume shift detected."
        else:
            msg += "\n\n **Status:** Operations expected to remain stable."
            
        return msg