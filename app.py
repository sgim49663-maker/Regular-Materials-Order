import streamlit as st
import datetime
import httpx
from supabase import create_client, Client
import os

# ============================================
# 설정
# ============================================
st.set_page_config(
    page_title="🧪 실험실 물품 주문 관리",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Supabase 연결 (SSL 검증 비활성화)
SUPABASE_URL = os.environ.get("SUPABASE_URL", st.secrets.get("SUPABASE_URL", ""))
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", st.secrets.get("SUPABASE_KEY", ""))

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("⚠️ Supabase URL과 Key를 설정해주세요. (.streamlit/secrets.toml 또는 환경변수)")
    st.stop()

# ★ SSL 우회: 회사/기관 네트워크 자체서명 인증서 대응
@st.cache_resource
def init_supabase():
    """SSL 검증을 비활성화한 Supabase 클라이언트 생성"""
    # httpx 클라이언트를 SSL 검증 없이 생성
    custom_httpx = httpx.Client(verify=False)

    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # postgrest(DB 쿼리) 클라이언트의 세션을 SSL 비활성화 버전으로 교체
    client.postgrest.session = httpx.Client(
        base_url=f"{SUPABASE_URL}/rest/v1",
        headers=client.postgrest.session.headers,
        verify=False
    )

    return client

supabase = init_supabase()

# SSL 경고 숨기기
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")


# ============================================
# 유틸리티 함수
# ============================================
def fetch_items(vendor_filter=None, show_hidden=False):
    """물품 목록 조회"""
    query = supabase.table("items").select("*")
    if vendor_filter and vendor_filter != "전체":
        query = query.eq("vendor", vendor_filter)
    query = query.eq("hidden", show_hidden)
    result = query.order("last_order_date", desc=False).execute()
    return result.data


def toggle_hidden(item_id, hidden):
    """물품 숨김/표시 토글"""
    supabase.table("items").update({
        "hidden": hidden
    }).eq("id", item_id).execute()


def fetch_order_history(item_id):
    """특정 물품의 주문 이력 조회"""
    result = (
        supabase.table("order_history")
        .select("*")
        .eq("item_id", item_id)
        .order("order_date", desc=True)
        .execute()
    )
    return result.data


def update_last_order_date(item_id, new_date, old_date=None):
    """마지막 주문일 변경 + 이력 추가"""
    supabase.table("items").update({
        "last_order_date": new_date.isoformat()
    }).eq("id", item_id).execute()

    # 주문 이력에 추가
    supabase.table("order_history").insert({
        "item_id": item_id,
        "order_date": new_date.isoformat(),
        "memo": f"주문일 변경 ({old_date} → {new_date})" if old_date else "주문일 등록"
    }).execute()


def add_new_item(vendor, cat_no, name, total_orders, avg_qty,
                 min_cycle, avg_cycle, std_cycle, regularity, last_order_date):
    """새 물품 추가"""
    result = supabase.table("items").insert({
        "vendor": vendor,
        "cat_no": cat_no,
        "name": name,
        "total_orders": total_orders,
        "avg_order_qty": avg_qty,
        "min_cycle_days": min_cycle,
        "avg_cycle_days": avg_cycle,
        "cycle_std_days": std_cycle,
        "cycle_regularity": regularity,
        "last_order_date": last_order_date.isoformat()
    }).execute()

    # 주문 이력에도 추가
    if result.data:
        item_id = result.data[0]["id"]
        supabase.table("order_history").insert({
            "item_id": item_id,
            "order_date": last_order_date.isoformat(),
            "memo": "신규 물품 등록"
        }).execute()
    return result


def delete_item(item_id):
    """물품 삭제"""
    supabase.table("order_history").delete().eq("item_id", item_id).execute()
    supabase.table("items").delete().eq("id", item_id).execute()


def calc_dday(last_order_date_str, cycle_days):
    """D-day 계산: 목표일(마지막주문일+주기) - 오늘"""
    last_order = datetime.date.fromisoformat(last_order_date_str)
    target_date = last_order + datetime.timedelta(days=int(round(cycle_days)))
    today = datetime.date.today()
    return (target_date - today).days, target_date


# ============================================
# CSS 스타일
# ============================================
st.markdown("""
<style>
    .dday-danger {
        background-color: #ff4b4b;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 1.0em;
        display: inline-block;
    }
    .dday-warning {
        background-color: #ffa726;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 1.0em;
        display: inline-block;
    }
    .dday-safe {
        background-color: #66bb6a;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 1.0em;
        display: inline-block;
    }
    .dday-overdue {
        background-color: #b71c1c;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 1.0em;
        animation: blink 1s infinite;
        display: inline-block;
    }
    @keyframes blink {
        50% { opacity: 0.5; }
    }
    .vendor-tag-kb {
        background-color: #1976d2;
        color: white;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.85em;
    }
    .vendor-tag-koram {
        background-color: #7b1fa2;
        color: white;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.85em;
    }
    .item-card {
        border: 1px solid #e0e0e0;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 8px;
        transition: box-shadow 0.2s;
    }
    .item-card:hover {
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)


# ============================================
# 사이드바
# ============================================
with st.sidebar:
    st.title("🧪 실험실 물품 관리")
    st.divider()

    # D-day 기준 선택
    cycle_mode = st.radio(
        "📅 D-day 기준 주기",
        ["최소 주문주기", "평균 주문주기"],
        index=0,
        help="최소 주문주기: 가장 빨랐던 주문 간격 기준\n평균 주문주기: 평균 주문 간격 기준"
    )

    st.divider()

    # 업체 필터
    vendor_filter = st.selectbox(
        "🏢 업체 필터",
        ["전체", "케이바이오", "코람"]
    )

    st.divider()

    # 숨긴 물품 보기
    show_hidden = st.toggle("🙈 숨긴 물품 보기", value=False)

    st.divider()

    # 새 물품 추가
    st.subheader("➕ 새 물품 추가")
    with st.form("add_item_form"):
        new_vendor = st.selectbox("업체", ["케이바이오", "코람"], key="new_vendor")
        new_cat_no = st.text_input("Cat #", key="new_cat")
        new_name = st.text_input("품명", key="new_name")

        col_a, col_b = st.columns(2)
        with col_a:
            new_total = st.number_input("총 주문 횟수", min_value=0, value=1, key="new_total")
            new_min_cycle = st.number_input("최소 주문주기(일)", min_value=1, value=30, key="new_min")
            new_std = st.number_input("주기 표준편차(일)", min_value=0.0, value=0.0, key="new_std")
        with col_b:
            new_avg_qty = st.number_input("평균 주문수량", min_value=0.1, value=1.0, step=0.1, key="new_qty")
            new_avg_cycle = st.number_input("평균 주문주기(일)", min_value=1.0, value=30.0, step=0.1, key="new_avg")
            new_regularity = st.selectbox("주기 규칙성", ["규칙적", "불규칙"], key="new_reg")

        new_last_order = st.date_input("마지막 주문일", value=datetime.date.today(), key="new_date")

        submitted = st.form_submit_button("✅ 물품 추가", use_container_width=True)
        if submitted:
            if not new_cat_no or not new_name:
                st.error("Cat #과 품명을 입력해주세요.")
            else:
                try:
                    add_new_item(
                        new_vendor, new_cat_no, new_name,
                        new_total, new_avg_qty,
                        new_min_cycle, new_avg_cycle, new_std,
                        new_regularity, new_last_order
                    )
                    st.success(f"✅ '{new_name}' 추가 완료!")
                    st.rerun()
                except Exception as e:
                    st.error(f"오류: {e}")


# ============================================
# 메인 화면
# ============================================
if show_hidden:
    st.title("🙈 숨긴 물품 리스트")
else:
    st.title("📋 정기 주문 물품 리스트")

today = datetime.date.today()
st.caption(f"오늘: **{today.strftime('%Y년 %m월 %d일')}** | D-day 기준: **{cycle_mode}**")

# 데이터 로드
items = fetch_items(vendor_filter, show_hidden=show_hidden)

if not items:
    if show_hidden:
        st.info("숨긴 물품이 없습니다.")
    else:
        st.info("등록된 물품이 없습니다. 사이드바에서 물품을 추가해주세요.")
    st.stop()

# D-day 계산 및 정렬
for item in items:
    cycle_days = item["min_cycle_days"] if cycle_mode == "최소 주문주기" else item["avg_cycle_days"]
    dday, target = calc_dday(item["last_order_date"], cycle_days)
    item["_dday"] = dday
    item["_target_date"] = target
    item["_cycle_used"] = cycle_days

# D-day 오름차순 정렬 (긴급한 것이 위로)
items.sort(key=lambda x: x["_dday"])

# 통계 요약
overdue = sum(1 for i in items if i["_dday"] < 0)
urgent = sum(1 for i in items if 0 <= i["_dday"] <= 7)
normal = len(items) - overdue - urgent

col1, col2, col3, col4 = st.columns(4)
col1.metric("📦 전체 물품", f"{len(items)}개")
col2.metric("🔴 기한 초과", f"{overdue}개")
col3.metric("🟠 7일 이내", f"{urgent}개")
col4.metric("🟢 여유", f"{normal}개")

st.divider()

# ============================================
# 물품 리스트 표시
# ============================================
for item in items:
    dday = item["_dday"]
    target_date = item["_target_date"]
    cycle_used = item["_cycle_used"]

    # D-day 스타일 결정
    if dday < 0:
        dday_html = f'<span class="dday-overdue">⚠️ D+{abs(dday)} 초과!</span>'
        border_color = "#b71c1c"
    elif dday <= 7:
        dday_html = f'<span class="dday-danger">🔴 D-{dday}</span>'
        border_color = "#ff4b4b"
    elif dday <= 14:
        dday_html = f'<span class="dday-warning">🟠 D-{dday}</span>'
        border_color = "#ffa726"
    else:
        dday_html = f'<span class="dday-safe">🟢 D-{dday}</span>'
        border_color = "#66bb6a"

    # 업체 태그
    if item["vendor"] == "케이바이오":
        vendor_html = '<span class="vendor-tag-kb">케이바이오</span>'
    else:
        vendor_html = '<span class="vendor-tag-koram">코람</span>'

    # 카드 표시
    with st.container():
        st.markdown(
            f"""<div class="item-card" style="border-left: 4px solid {border_color};">
                {vendor_html} &nbsp; {dday_html}
                &nbsp;&nbsp; <strong>{item["name"]}</strong>
                <span style="color: #888; font-size: 0.85em;"> | Cat# {item["cat_no"]}</span>
            </div>""",
            unsafe_allow_html=True
        )

        with st.expander(f"📋 상세 정보 — {item['name'][:30]}...", expanded=False):
            info_col, action_col = st.columns([3, 2])

            with info_col:
                st.markdown(f"""
                | 항목 | 값 |
                |---|---|
                | **업체** | {item['vendor']} |
                | **Cat #** | `{item['cat_no']}` |
                | **총 주문 횟수** | {item['total_orders']}회 |
                | **평균 주문수량** | {item['avg_order_qty']}개 |
                | **최소 주문주기** | {item['min_cycle_days']}일 |
                | **평균 주문주기** | {item['avg_cycle_days']}일 |
                | **표준편차** | {item['cycle_std_days']}일 |
                | **규칙성** | {item['cycle_regularity']} |
                | **마지막 주문일** | {item['last_order_date']} |
                | **목표 주문일** | {target_date.strftime('%Y-%m-%d')} (적용 주기: {cycle_used}일) |
                """)

            with action_col:
                st.markdown("##### 📅 마지막 주문일 변경")
                new_date = st.date_input(
                    "새 주문일",
                    value=datetime.date.fromisoformat(item["last_order_date"]),
                    key=f"date_{item['id']}"
                )
                if st.button("💾 주문일 저장", key=f"save_{item['id']}"):
                    old_date = item["last_order_date"]
                    update_last_order_date(item["id"], new_date, old_date)
                    st.success(f"✅ 주문일 변경: {old_date} → {new_date}")
                    st.rerun()

                st.markdown("---")

                # 주문 이력 보기
                st.markdown("##### 📜 주문 이력")
                if st.button("이력 조회", key=f"hist_{item['id']}"):
                    st.session_state[f"show_hist_{item['id']}"] = True

                if st.session_state.get(f"show_hist_{item['id']}", False):
                    history = fetch_order_history(item["id"])
                    if history:
                        for h in history:
                            st.markdown(
                                f"- **{h['order_date']}** {' — ' + h['memo'] if h.get('memo') else ''}"
                            )
                    else:
                        st.caption("이력이 없습니다.")

                st.markdown("---")

                # 숨기기/보이기 버튼
                if show_hidden:
                    if st.button("👁️ 다시 표시", key=f"show_{item['id']}"):
                        toggle_hidden(item["id"], False)
                        st.rerun()
                else:
                    if st.button("🙈 숨기기", key=f"hide_{item['id']}"):
                        toggle_hidden(item["id"], True)
                        st.rerun()

                st.markdown("---")

                # 삭제 버튼
                if st.button("🗑️ 물품 삭제", key=f"del_{item['id']}", type="secondary"):
                    st.session_state[f"confirm_del_{item['id']}"] = True

                if st.session_state.get(f"confirm_del_{item['id']}", False):
                    st.warning(f"⚠️ '{item['name']}'을(를) 정말 삭제하시겠습니까?")
                    c1, c2 = st.columns(2)
                    if c1.button("✅ 확인", key=f"yes_del_{item['id']}"):
                        delete_item(item["id"])
                        st.session_state[f"confirm_del_{item['id']}"] = False
                        st.rerun()
                    if c2.button("❌ 취소", key=f"no_del_{item['id']}"):
                        st.session_state[f"confirm_del_{item['id']}"] = False
                        st.rerun()


# ============================================
# 푸터
# ============================================
st.divider()
st.caption("🧬 실험실 물품 주문 관리 시스템 | Streamlit + Supabase")
