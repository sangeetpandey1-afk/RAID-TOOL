# Master Data — Sample Files & Column Reference

ये फोल्डर 6 **`SAMPLE_*.xlsx`** workbooks रखता है जो दिखाते हैं कि **असली production
Excel files में किस heading के साथ कौन सा column होना चाहिए** ताकि
`/api/import_all_master_data` बिना किसी HTTP 500 के सब import कर ले।

> 💡 अपनी असली file को इन sample files के साथ side-by-side खोलो और headings मिला लो।
> Importer **case / space / punctuation insensitive** है, और हर field के लिए कई synonyms accept करता है, फिर भी canonical headings use करना सबसे safe है।

---

## 📂 Files at a glance

| Sample File | Target Table | Production File (typical) | Required Column | Idempotent Key |
|-------------|--------------|---------------------------|-----------------|----------------|
| `SAMPLE_raid_master_data.xlsx` | `consumers` | `raid_master_data.xlsx` (~69k) | `ACCT_ID` | `account_number` (UPSERT) |
| `SAMPLE_all_data.xlsx` | `historical_cases` | `ALL DATA.xlsx` (~8,956) | none (skip if no name+account) | INSERT-only |
| `SAMPLE_raid_excell_2526.xlsx` | `current_cases` | `raid excell 2526 Copy.xlsx` (~24k) | `ONLINE NO` (recommended) | `online_no` (UPSERT) |
| `SAMPLE_device_list.xlsx` | `device_master` | `device list.xlsx` (38) | `Device Name` | `device_name` (UPSERT) |
| `SAMPLE_slab_rates.xlsx` | `rate_master` | `slab_rates.xlsx` (24) | `Category` | INSERT-only (history kept) |
| `SAMPLE_account_mapping.xlsx` | `account_mapping` | `account_mapping.xlsx` (optional) | one of old/new account | INSERT-only |

> File-name detection is fuzzy too: anything containing `raid_master_data`, `consumer_master`, `master_data` etc. is picked as the consumer file. See `FILE_PATTERNS` in `backend/services/importer.py`.

---

## 1️⃣ `SAMPLE_raid_master_data.xlsx` → `consumers` table

| DB field | Sample column heading | Synonyms accepted (case/space/punct ignored) | Required? |
|----------|-----------------------|----------------------------------------------|-----------|
| account_number | **ACCT_ID** | `account_id`, `account no`, `acno`, `k_no`, `service no`, `connection_no`, `consumer_id` | ✅ **YES** |
| name | NAME | `consumer_name`, `customer_name`, `नाम`, `उपभोक्ता` | recommended |
| father_name | FATHER_NAME | `father`, `father/husband`, `पिता` | recommended |
| address | ADDRESS | `addr`, `premises`, `पता` | optional |
| village | VILLAGE | `ward`, `mohalla`, `ग्राम` | optional |
| landmark | LANDMARK | `near`, `नजदीक` | optional |
| post_office | POST | `post_office`, `po`, `डाकघर` | optional |
| pin_code | PIN | `pincode`, `zip` | optional |
| tehsil | TEHSIL | `tahsil`, `तहसील` | optional |
| district | DISTRICT | `जिला` | optional |
| mobile | MOBILE_NO | `mobile`, `phone`, `contact`, `मोबाइल` | optional |
| load_value | LOAD | `connected_load`, `load_kw`, `sanctioned_load` | optional |
| load_unit | LOAD_UNIT | `loadunit`, `unit` | optional |
| supply_type | SUPPLY_TYPE | `supplytype`, `supply` | optional |
| category | CATEGORY | `tariff_category`, `rate_category`, `lmv` | optional |
| sub_substation | SUB_SUBSTATION | `substation`, `ss` | optional |
| connection_status | CON_STATUS | `connection_status`, `status` | optional |
| div_code | DIV_CODE | `div_no`, `division`, `divcode` | optional |
| sc_number | SC_NO | `sc_number`, `service_connection`, `service_no` | optional |

**Behavior:** Same `ACCT_ID` re-imported → row is **UPDATED in place** (no duplicates).

---

## 2️⃣ `SAMPLE_all_data.xlsx` → `historical_cases` table

| DB field | Sample column heading | Synonyms accepted |
|----------|-----------------------|-------------------|
| div_no | div no | `divno`, `division`, `div` |
| name | Name | `consumer_name`, `नाम` |
| father_name | father name | `father`, `पिता` |
| village | village | `ग्राम` |
| account_id | Account Id | `acct_id`, `account_no`, `acno`, `k_no` |
| case_date | Date | `case_date`, `raid_date`, `inspection_date`, `तिथि`, `दिनांक` |
| assessment_amount | assessment | `amount`, `राशि` |
| fir_number | FIR | `fir_no`, `एफआईआर` |
| section | dhara | `section`, `धारा` |

**Behavior:** Always INSERT (history is append-only). Date is auto-parsed from Excel date / `dd/mm/yyyy` / `yyyy-mm-dd`.

---

## 3️⃣ `SAMPLE_raid_excell_2526.xlsx` → `current_cases` table

| DB field | Sample column heading | Synonyms accepted | Required? |
|----------|-----------------------|-------------------|-----------|
| online_no | **ONLINE NO** | `onlineno`, `online_number` | ✅ recommended (UPSERT key) |
| div_no | div no | `divno`, `division` | optional |
| name | Name | `consumer_name`, `नाम` | optional |
| father_name | father name | `father`, `पिता` | optional |
| village | village | `ग्राम` | optional |
| connection_no | connection no | `conn_no`, `account_id`, `acno` | optional |
| inspection_date | inspection_date | `date`, `raid_date`, `dis_date`, `checking_date` | optional |
| section | section | `dhara`, `धारा` (135 / 138 / 126 / Other) | optional |
| total_assessment | assessment_total | `assessment`, `total`, `amount` | optional |
| notice_status | notice_status | `notice`, `notice_state` | optional |
| payment_status | payment_status | `paid`, `pay_state` | optional |

**Behavior:** Same `ONLINE NO` re-imported → row is UPDATED. Missing `ONLINE NO` → row is INSERTED as new.

---

## 4️⃣ `SAMPLE_device_list.xlsx` → `device_master` table

| DB field | Sample column heading | Synonyms accepted | Default if missing |
|----------|-----------------------|-------------------|--------------------|
| device_name | **Device Name** | `device`, `name`, `equipment`, `उपकरण` | ✅ required |
| category | Category | `type`, `group`, `श्रेणी` | NULL |
| default_load | Load (W) | `wattage`, `watts`, `power`, `load_w` | NULL |
| default_factor | Factor | `diversity`, `df`, `f` | **1.0** |
| default_hours | Hours | `h`, `duration` | **8** |
| default_days | Days | `d` | **365** |
| unit | Unit | `uom` | `Nos` |

**Behavior:** Same `Device Name` re-imported → UPDATE. **40 default devices auto-seeded** on first DB init even without this file.
**Categories used in spec:** Lighting, Cooling, Heating, Washing, Kitchen, Pumping, Electronics, Misc.

---

## 5️⃣ `SAMPLE_slab_rates.xlsx` → `rate_master` table

| DB field | Sample column heading | Synonyms accepted | Notes |
|----------|-----------------------|-------------------|-------|
| category | **Category** | `tariff_category`, `lmv` | ✅ required (LMV-1 … LMV-9) |
| slab_start | SlabStart | `from`, `lower_limit`, `min_units` | integer (units) |
| slab_end | SlabEnd | `to`, `upper_limit`, `max_units` | **blank = unlimited (top slab)** |
| rate_per_unit | RatePerUnit | `rate`, `tariff`, `energy_rate` | ₹ per unit |
| fixed_charge | FixedCharge | `fixed`, `fixed_rate`, `monthly_fixed` | ₹ per month |
| duty_percent | DutyPercent | `duty`, `ed`, `electricity_duty` | 0 / 5 / 7.5 |
| condition | Condition | `remark`, `note` | free text |
| effective_date | EffectiveDate | `from_date`, `valid_from` | tariff history |
| end_date | (none in sample) | `to_date`, `valid_to` | optional |

**Behavior:** Always INSERT — to keep tariff history. Use `effective_date` / `end_date` to mark validity windows. Multiple rows per category form the slab ladder (e.g. `0-100, 101-200, 201-300, 301-NULL`).

---

## 6️⃣ `SAMPLE_account_mapping.xlsx` → `account_mapping` table

Used by **Level-3 offense detection** (old↔new account bridge via SC number).

| DB field | Sample column heading | Synonyms |
|----------|-----------------------|----------|
| old_account | Old Account | `old_acno`, `previous_account` |
| new_account | New Account | `new_acno`, `current_account`, `account` |
| sc_number | SC Number | `sc_no`, `service_connection` |
| consumer_name | Consumer Name | `name`, `customer_name` |
| father_name | Father Name | `father` |
| village | Village | — |
| effective_date | Effective Date | `from_date`, `date` |
| status | Status | `active`, `is_active` |

**Behavior:** INSERT-only. At least one of Old / New account must be filled.

---

## 🔁 Re-generating these sample files

Agar columns ki list update karni ho ya naye sample rows daalne ho:

```bash
python scripts/generate_sample_excels.py
```

Script `scripts/generate_sample_excels.py` me 6 Python lists (`CONSUMERS`,
`HISTORICAL`, `CURRENT`, `DEVICES`, `RATES`, `MAPPINGS`) edit karke fir se chalao.

---

## 🧪 Verifying your real file before bulk import

```bash
# 1. Apni file ko master_data/ me copy karo (recommended naming):
#    raid_master_data.xlsx, ALL DATA.xlsx, raid excell 2526.xlsx,
#    device list.xlsx, slab_rates.xlsx, account_mapping.xlsx
#
# 2. Check which file got picked + which columns mapped:
curl http://localhost:5000/api/master_files

# 3. Dry-run a single kind:
curl -X POST http://localhost:5000/api/import_master/consumers

# 4. Full import:
curl -X POST http://localhost:5000/api/import_all_master_data
```

Response me `column_mapping` dictionary aur `errors_sample` mil jayega — agar
koi field unmapped hai, response me `warnings` me mention ho jayega bina
import rok ke (per-row try/except hai).
