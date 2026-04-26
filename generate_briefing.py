import json

def generate_briefing(snapshot_path, kb_path):
    # Load data
    with open(snapshot_path, 'r') as f:
        snapshot = json.load(f)
    with open(kb_path, 'r') as f:
        kb = json.load(f)
        
    # Map pair names to KB pattern IDs based on current correlation sign
    # This logic determines which regime pattern applies based on the pair and its 30d correlation
    def get_pattern_id(pair_name, corr_30d):
        if pair_name == 'oil_vs_spx' and corr_30d < 0:
            return 'oil_spx_negative'
        elif pair_name == 'gold_vs_real_yield_10y':
            return 'gold_real_yield_positive' if corr_30d > 0 else 'gold_real_yield_negative'
        elif pair_name == 'dxy_vs_em_eq':
            return 'dxy_em_positive' if corr_30d > 0 else 'dxy_em_negative'
        elif pair_name == 'yield_spread_vs_spx':
            return 'yield_curve_inverted_spx_falling'
        # Fallback or unmapped pairs
        return None

    # Build KB lookup dictionary
    kb_dict = {pattern['pattern_id']: pattern for pattern in kb}
    
    briefings = []
    
    # Process flagged pairs
    for pair_data in snapshot.get('pairs', []):
        if not pair_data.get('regime_shift_flag'):
            continue
            
        pair_name = pair_data['pair_name']
        corr_30d = pair_data['corr_30d']
        
        pattern_id = get_pattern_id(pair_name, corr_30d)
        if not pattern_id or pattern_id not in kb_dict:
            continue
            
        pattern = kb_dict[pattern_id]
        
        # Extract historical periods
        historical_periods = [inst['period'] for inst in pattern.get('historical_instances', [])]
        
        # Generate plain English summary
        # Format pair name for readability
        readable_pair = pair_name.replace('_vs_', ' and ').replace('_', ' ').title()
        if pair_name == 'dxy_vs_em_eq':
            readable_pair = 'The US Dollar (DXY) and Emerging Market Equities'
        elif pair_name == 'yield_spread_vs_spx':
            readable_pair = 'The Yield Spread and the S&P 500'
            
        correlation_type = "positively" if corr_30d > 0 else "negatively"
        
        summary = f"{readable_pair} are currently {correlation_type} correlated at {corr_30d:.2f}. "
        summary += f"Historically, this pattern signals a '{pattern['macro_theme']}' regime. "
        
        if len(historical_periods) > 0:
            last_episode = pattern['historical_instances'][-1]
            res_text = last_episode['resolution']
            # Make the resolution text flow better in the sentence
            if res_text[0].isupper():
                res_text = res_text[0].lower() + res_text[1:]
            if res_text.endswith('.'):
                res_text = res_text[:-1]
            summary += f"The last major episode occurred in {last_episode['period']} and resolved when {res_text}."
            
        briefing = {
            "pair": pair_name,
            "current_correlation": round(corr_30d, 4),
            "regime_theme": pattern['macro_theme'],
            "historical_analogs": historical_periods,
            "plain_english_summary": summary,
            "watch_list": pattern.get('warning_signals', [])
        }
        
        briefings.append(briefing)
        
    return briefings

if __name__ == "__main__":
    snapshot_file = '/home/ubuntu/latest_snapshot.json'
    kb_file = '/home/ubuntu/macro_regimes_kb.json'
    
    results = generate_briefing(snapshot_file, kb_file)
    
    print(json.dumps(results, indent=2))
    
    # Export to file
    with open('/home/ubuntu/morning_briefing.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("\nBriefing exported to /home/ubuntu/morning_briefing.json")
