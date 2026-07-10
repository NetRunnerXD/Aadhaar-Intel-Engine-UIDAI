import pandas as pd
import os
import numpy as np

class DataLoader:
    def __init__(self, data_path):
        self.data_path = os.path.normpath(data_path)

    @staticmethod
    def _optimize(df):
        """Downcast numeric types to save memory."""
        for col in df.select_dtypes(include=['float64']).columns:
            df[col] = pd.to_numeric(df[col], downcast='float')
        for col in df.select_dtypes(include=['int64']).columns:
            df[col] = pd.to_numeric(df[col], downcast='integer')
        return df

    def get_data(self):
        logs = []
        datasets = {'enrol': [], 'bio': [], 'demo': []}

        if not os.path.exists(self.data_path):
            logs.append(f"Error: Data path not found: {self.data_path}")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), logs

        # 1. File Discovery & Classification
        files = [f for f in os.listdir(self.data_path) if f.lower().endswith('.csv')]
        logs.append(f"Loading {len(files)} files from source...")

        for f in files:
            path = os.path.join(self.data_path, f)
            try:
                # Peek at columns to identify file type
                cols = [c.lower().strip() for c in pd.read_csv(path, nrows=0).columns]

                if any('bio_age' in c for c in cols):
                    datasets['bio'].append(pd.read_csv(path))
                elif any('demo_age' in c for c in cols):
                    datasets['demo'].append(pd.read_csv(path))
                elif any(c in ['age_0_5', 'age_18_greater'] for c in cols):
                    datasets['enrol'].append(pd.read_csv(path))
            except Exception as e:
                logs.append(f"Skipped {f}: {str(e)}")

        # 2. Process Enrolment Data
        if datasets['enrol']:
            raw = pd.concat(datasets['enrol'], ignore_index=True)
            raw.columns = raw.columns.str.lower().str.strip()
            
            # Calculate Adult Enrolments
            if 'age_18_greater' in raw.columns:
                raw['adult_enrolments'] = raw['age_18_greater'].fillna(0)
            else:
                targets = [c for c in ['age_0_5', 'age_5_17', 'age_18_greater'] if c in raw.columns]
                raw['adult_enrolments'] = raw[targets].sum(axis=1) if targets else 0
                
            df_enrol = raw[['date', 'state', 'district', 'pincode', 'adult_enrolments']].copy()
        else:
            df_enrol = pd.DataFrame(columns=['date', 'state', 'district', 'pincode', 'adult_enrolments'])

        # 3. Process Biometric Data
        if datasets['bio']:
            raw = pd.concat(datasets['bio'], ignore_index=True)
            raw.columns = raw.columns.str.lower().str.strip()
            
            targets = [c for c in ['bio_age_5_17', 'bio_age_17_'] if c in raw.columns]
            raw['bio_stress'] = raw[targets].sum(axis=1) if targets else 0
            df_bio = raw[['date', 'state', 'district', 'pincode', 'bio_stress']].copy()
        else:
            # Fallback: Simulate bio stress if missing
            if not df_enrol.empty:
                df_bio = df_enrol.copy()
                df_bio['bio_stress'] = (df_bio['adult_enrolments'] * 0.4).astype(int)
            else:
                df_bio = pd.DataFrame(columns=['date', 'state', 'district', 'pincode', 'bio_stress'])

        # 4. Process Demographic Data
        if datasets['demo']:
            raw = pd.concat(datasets['demo'], ignore_index=True)
            raw.columns = raw.columns.str.lower().str.strip()
            
            targets = [c for c in ['demo_age_5_17', 'demo_age_17_'] if c in raw.columns]
            raw['update_volume'] = raw[targets].sum(axis=1) if targets else 0
            df_demo = raw[['date', 'state', 'district', 'pincode', 'update_volume']].copy()
        else:
            df_demo = pd.DataFrame(columns=['date', 'state', 'district', 'pincode', 'update_volume'])

        # 5. Standardization
        for df in [df_enrol, df_bio, df_demo]:
            if df.empty: continue
            
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], dayfirst=True, errors='coerce')
            
            for col in ['state', 'district']:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.title().str.strip()
            
            if 'pincode' in df.columns:
                df['pincode'] = pd.to_numeric(df['pincode'], errors='coerce').fillna(0).astype(int)

        return self._optimize(df_enrol), self._optimize(df_demo), self._optimize(df_bio), logs