import os

import requests
import pandas as pd
import streamlit as st


# ============================================================
# CONFIGURATION
# ============================================================

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Well Slippage Dashboard",
    page_icon="🔎",
    layout="wide"
)


# ============================================================
# HEADER
# ============================================================

st.title("🔎 Well Slippage Dashboard")

st.caption(
    "Well slippage monitoring and investigation"
)


# ============================================================
# API FUNCTIONS
# ============================================================

def get_slipped_wells():
    """
    Get the list of slipped wells from FastAPI.
    """

    response = requests.get(
        f"{API_URL}/api/slipped-wells",
        timeout=60
    )

    response.raise_for_status()

    return response.json()


def check_well(well_id):
    """
    Send the selected well ID to FastAPI.

    FastAPI will:
        1. Execute investigation SQL
        2. Use the selected well_id
        3. Convert the result to JSON
        4. Update investigation.json in backend
    """

    response = requests.get(
        f"{API_URL}/api/well/{well_id}/investigation",
        timeout=300
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# LOAD SLIPPED WELLS
# ============================================================

try:

    result = get_slipped_wells()

except requests.exceptions.ConnectionError:

    st.error(
        "❌ Cannot connect to the FastAPI backend."
    )

    st.info(
        "Make sure FastAPI is running:"
    )

    st.code(
        "uvicorn main:app --reload"
    )

    st.stop()


except requests.exceptions.Timeout:

    st.error(
        "❌ The request to FastAPI timed out."
    )

    st.stop()


except requests.exceptions.HTTPError as e:

    st.error(
        f"❌ FastAPI returned an HTTP error: {e}"
    )

    st.stop()


except requests.exceptions.RequestException as e:

    st.error(
        f"❌ API request failed: {e}"
    )

    st.stop()


except Exception as e:

    st.error(
        f"❌ Unexpected error: {e}"
    )

    st.stop()


# ============================================================
# VALIDATE API RESPONSE
# ============================================================

if not isinstance(result, dict):

    st.error(
        "❌ Invalid response received from backend."
    )

    st.stop()


if not result.get("success", False):

    st.error(
        "❌ Failed to retrieve slipped wells."
    )

    st.stop()


# ============================================================
# GET WELL LIST
# ============================================================

wells = result.get(
    "wells",
    []
)


df = pd.DataFrame(
    wells
)


# ============================================================
# CHECK DATA
# ============================================================

if df.empty:

    st.success(
        "✅ No slipped wells found."
    )

    st.stop()


# ============================================================
# CHECK WELL ID
# ============================================================

if "well_id" not in df.columns:

    st.error(
        "❌ `well_id` is missing from the backend response."
    )

    st.stop()


# ============================================================
# CLEAN WELL ID
# ============================================================

df["well_id"] = pd.to_numeric(
    df["well_id"],
    errors="coerce"
)


df = df.dropna(
    subset=["well_id"]
)


df["well_id"] = (
    df["well_id"]
    .astype(int)
)


# ============================================================
# KPI SECTION
# ============================================================

st.divider()

col1, col2, col3 = st.columns(3)


# ------------------------------------------------------------
# KPI 1
# ------------------------------------------------------------

with col1:

    st.metric(
        "Slipped Wells",
        df["well_id"].nunique()
    )


# ------------------------------------------------------------
# KPI 2
# ------------------------------------------------------------

with col2:

    if "rig_id" in df.columns:

        rig_count = (
            df["rig_id"]
            .dropna()
            .nunique()
        )

        st.metric(
            "Rigs",
            rig_count
        )

    else:

        st.metric(
            "Rigs",
            "N/A"
        )


# ------------------------------------------------------------
# KPI 3
# ------------------------------------------------------------

with col3:

    st.metric(
        "Records",
        len(df)
    )


# ============================================================
# SLIPPED WELLS TABLE
# ============================================================

st.divider()

st.subheader(
    "📋 Slipped Wells"
)


display_columns = [

    "well_id",

    "project_id",

    "rig_id",

    "well_type_id",

    "station_id",

    "ex_rig_on_date",

    "rig_on_date",

    "ex_rig_off_date",

    "rig_off_date"
]


available_columns = [

    column
    for column in display_columns
    if column in df.columns

]


if available_columns:

    display_df = df[
        available_columns
    ].copy()


    # --------------------------------------------------------
    # Friendly column names
    # --------------------------------------------------------

    rename_columns = {

        "well_id":
            "Well ID",

        "project_id":
            "Project ID",

        "rig_id":
            "Rig",

        "well_type_id":
            "Well Type",

        "station_id":
            "Station",

        "ex_rig_on_date":
            "Expected Rig On",

        "rig_on_date":
            "Actual Rig On",

        "ex_rig_off_date":
            "Expected Rig Off",

        "rig_off_date":
            "Actual Rig Off"
    }


    display_df = display_df.rename(
        columns=rename_columns
    )


    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# WELL SELECTION
# ============================================================

st.divider()

st.subheader(
    "🔍 Select a Slipped Well"
)


well_ids = sorted(
    df["well_id"]
    .unique()
    .tolist()
)


selected_well = st.selectbox(
    "Well",
    well_ids,
    key="selected_well"
)


# ============================================================
# SELECTED WELL DATA
# ============================================================

selected_data = df[
    df["well_id"] == selected_well
]


if selected_data.empty:

    st.warning(
        "No data found for the selected well."
    )

    st.stop()


selected_row = (
    selected_data.iloc[0]
)


# ============================================================
# SELECTED WELL
# ============================================================

st.subheader(
    f"Selected Well: {selected_well}"
)


# ============================================================
# WELL INFORMATION
# ============================================================

col1, col2, col3, col4 = st.columns(4)


# ------------------------------------------------------------
# WELL ID
# ------------------------------------------------------------

with col1:

    st.caption(
        "Well ID"
    )

    st.write(
        f"**{selected_well}**"
    )


# ------------------------------------------------------------
# RIG
# ------------------------------------------------------------

with col2:

    st.caption(
        "Rig"
    )

    rig = selected_row.get(
        "rig_id",
        None
    )


    if pd.isna(rig):

        rig = "N/A"


    st.write(
        f"**{rig}**"
    )


# ------------------------------------------------------------
# EXPECTED RIG ON
# ------------------------------------------------------------

with col3:

    st.caption(
        "Expected Rig On"
    )

    expected_rig_on = selected_row.get(
        "ex_rig_on_date",
        None
    )


    if pd.notna(expected_rig_on):

        st.write(
            f"**{expected_rig_on}**"
        )

    else:

        st.write(
            "**N/A**"
        )


# ------------------------------------------------------------
# ACTUAL RIG ON
# ------------------------------------------------------------

with col4:

    st.caption(
        "Actual Rig On"
    )

    actual_rig_on = selected_row.get(
        "rig_on_date",
        None
    )


    if pd.notna(actual_rig_on):

        st.write(
            f"**{actual_rig_on}**"
        )

    else:

        st.write(
            "**Pending**"
        )


# ============================================================
# RIG-ON SLIPPAGE
# ============================================================

if (
    pd.notna(expected_rig_on)
    and
    pd.notna(actual_rig_on)
):

    try:

        expected_date = pd.to_datetime(
            expected_rig_on
        )

        actual_date = pd.to_datetime(
            actual_rig_on
        )

        slippage_days = (
            actual_date - expected_date
        ).days


        if slippage_days > 0:

            st.warning(
                f"⚠️ Rig-On Slippage: "
                f"**{slippage_days} days**"
            )


        elif slippage_days == 0:

            st.success(
                "Rig-On completed on schedule."
            )


        else:

            st.info(
                f"Rig-On completed "
                f"{abs(slippage_days)} days early."
            )


    except Exception:

        pass


# ============================================================
# PENDING RIG-ON
# ============================================================

elif pd.notna(expected_rig_on):

    try:

        expected_date = pd.to_datetime(
            expected_rig_on
        )

        today = (
            pd.Timestamp
            .today()
            .normalize()
        )


        if today > expected_date:

            pending_days = (
                today - expected_date
            ).days


            st.warning(
                f"⚠️ Rig-On is pending and "
                f"**{pending_days} days** past "
                f"the expected date."
            )


    except Exception:

        pass


# ============================================================
# WELL INVESTIGATION
# ============================================================

st.divider()

st.subheader(
    "🔎 Well Investigation"
)


st.write(
    "Click the button to check the selected well. "
    "The investigation result will be updated in the "
    "backend JSON file."
)


# ============================================================
# CHECK THIS WELL BUTTON
# ============================================================

if st.button(
    f"Check This Well — {selected_well}",
    type="primary",
    use_container_width=True
):

    with st.spinner(
        f"Checking Well {selected_well}..."
    ):

        try:

            investigation_result = check_well(
                selected_well
            )


            # =================================================
            # SUCCESS
            # =================================================

            if (
                investigation_result
                and
                investigation_result.get(
                    "success",
                    False
                )
            ):

                st.success(
                    f"✅ Well {selected_well} "
                    "checked successfully."
                )


                row_count = (
                    investigation_result.get(
                        "row_count"
                    )
                )


                if row_count is not None:

                    st.caption(
                        f"{row_count} rows processed "
                        "and investigation.json updated "
                        "in the backend."
                    )


            # =================================================
            # FAILURE
            # =================================================

            else:

                st.error(
                    f"❌ Failed to check "
                    f"Well {selected_well}."
                )


        # =====================================================
        # CONNECTION ERROR
        # =====================================================

        except requests.exceptions.ConnectionError:

            st.error(
                "❌ Could not connect to FastAPI."
            )

            st.info(
                "Make sure the backend is running:"
            )

            st.code(
                "uvicorn main:app --reload"
            )


        # =====================================================
        # TIMEOUT
        # =====================================================

        except requests.exceptions.Timeout:

            st.error(
                "❌ Investigation request timed out."
            )


        # =====================================================
        # HTTP ERROR
        # =====================================================

        except requests.exceptions.HTTPError as e:

            st.error(
                f"❌ Investigation API returned an error: {e}"
            )


            # Try to display backend error message
            # without displaying investigation JSON.

            try:

                error_data = e.response.json()

                if "detail" in error_data:

                    st.error(
                        str(
                            error_data["detail"]
                        )
                    )

            except Exception:

                pass


        # =====================================================
        # OTHER REQUEST ERROR
        # =====================================================

        except requests.exceptions.RequestException as e:

            st.error(
                f"❌ Investigation request failed: {e}"
            )


        # =====================================================
        # UNKNOWN ERROR
        # =====================================================

        except Exception as e:

            st.error(
                f"❌ Unexpected investigation error: {e}"
            )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Investigation data is stored in the backend. "
    "LLM analysis will be implemented in the next stage."
)
