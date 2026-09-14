import streamlit as st


def begin_chart_card(
    title,
    subtitle="",
    color="#ff9800"
):

    st.markdown(f"""
    <style>

    .dashboard-card {{

        background:white;

        border-radius:18px;

        overflow:hidden;

        box-shadow:0px 5px 15px rgba(0,0,0,.10);

        margin-bottom:20px;

        border:1px solid #ececec;

    }}

    .dashboard-header {{

        background:{color};

        color:white;

        padding:18px 25px;

    }}

    .dashboard-title {{

        font-size:24px;

        font-weight:700;

        margin:0;

    }}

    .dashboard-subtitle {{

        font-size:14px;

        opacity:.9;

        margin-top:4px;

    }}

    </style>

    <div class="dashboard-card">

        <div class="dashboard-header">

            <div class="dashboard-title">

                {title}

            </div>

            <div class="dashboard-subtitle">

                {subtitle}

            </div>

        </div>

    </div>

    """,
    unsafe_allow_html=True)

def open_card(title, subtitle=""):

    st.markdown(f"""
    <div class="card">

    <div class="card-title">
        {title}
    </div>

    <div class="card-subtitle">
        {subtitle}
    </div>
    """, unsafe_allow_html=True)


def close_card():

    st.markdown(
        "</div>",
        unsafe_allow_html=True
    )


def chart_title(title, subtitle=""):

    st.markdown(f"""
    <div class="chart-title">

        <h3>{title}</h3>

        <p>{subtitle}</p>

    </div>
    """,
    unsafe_allow_html=True)



def chart_card(title, subtitle, fig, key):

    with st.container(
        key=key,
        border=True
    ):

        st.subheader(title)

        st.caption(subtitle)

        st.plotly_chart(
            fig,
            use_container_width=True
        )

