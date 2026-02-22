--
-- PostgreSQL database dump
--

\restrict Rr7ubW39EMJXrdke2vRgkdC7AIuV7Ea3wqL7o6byKeqkRcpkeibkBJ4H8ah4bAD

-- Dumped from database version 18.2
-- Dumped by pg_dump version 18.2

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: postatus; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.postatus AS ENUM (
    'DRAFT',
    'SENT',
    'PARTIAL',
    'RECEIVED',
    'CANCELLED'
);


ALTER TYPE public.postatus OWNER TO postgres;

--
-- Name: roleenum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.roleenum AS ENUM (
    'admin',
    'cashier'
);


ALTER TYPE public.roleenum OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: applied_promotions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.applied_promotions (
    id integer NOT NULL,
    sale_id integer NOT NULL,
    promotion_id integer,
    promo_name character varying(200) NOT NULL,
    discount_amount numeric(12,2) NOT NULL,
    description character varying(300),
    CONSTRAINT check_applied_promotion_discount_non_negative CHECK ((discount_amount >= (0)::numeric))
);


ALTER TABLE public.applied_promotions OWNER TO postgres;

--
-- Name: applied_promotions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.applied_promotions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.applied_promotions_id_seq OWNER TO postgres;

--
-- Name: applied_promotions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.applied_promotions_id_seq OWNED BY public.applied_promotions.id;


--
-- Name: cash_sessions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cash_sessions (
    id integer NOT NULL,
    cashier_id integer NOT NULL,
    opening_cash numeric(10,2) NOT NULL,
    system_total numeric(12,2) NOT NULL,
    closing_cash numeric(10,2),
    start_time timestamp without time zone NOT NULL,
    end_time timestamp without time zone,
    CONSTRAINT check_cash_session_closing_non_negative CHECK (((closing_cash IS NULL) OR (closing_cash >= (0)::numeric))),
    CONSTRAINT check_cash_session_opening_non_negative CHECK ((opening_cash >= (0)::numeric)),
    CONSTRAINT check_cash_session_system_total_non_negative CHECK ((system_total >= (0)::numeric))
);


ALTER TABLE public.cash_sessions OWNER TO postgres;

--
-- Name: cash_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cash_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.cash_sessions_id_seq OWNER TO postgres;

--
-- Name: cash_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cash_sessions_id_seq OWNED BY public.cash_sessions.id;


--
-- Name: customers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.customers (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    phone character varying(20) NOT NULL,
    email character varying(120),
    points integer NOT NULL,
    created_at timestamp without time zone,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT check_customer_points_non_negative CHECK ((points >= 0))
);


ALTER TABLE public.customers OWNER TO postgres;

--
-- Name: customers_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.customers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.customers_id_seq OWNER TO postgres;

--
-- Name: customers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.customers_id_seq OWNED BY public.customers.id;


--
-- Name: gift_cards; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gift_cards (
    id integer NOT NULL,
    code character varying(50) NOT NULL,
    initial_balance numeric(10,2) NOT NULL,
    balance numeric(10,2) NOT NULL,
    created_at timestamp without time zone,
    is_active boolean,
    CONSTRAINT check_gift_card_balance_non_negative CHECK ((balance >= (0)::numeric)),
    CONSTRAINT check_gift_card_balance_within_initial CHECK ((balance <= initial_balance)),
    CONSTRAINT check_gift_card_initial_balance_non_negative CHECK ((initial_balance >= (0)::numeric))
);


ALTER TABLE public.gift_cards OWNER TO postgres;

--
-- Name: gift_cards_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.gift_cards_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gift_cards_id_seq OWNER TO postgres;

--
-- Name: gift_cards_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.gift_cards_id_seq OWNED BY public.gift_cards.id;


--
-- Name: goods_receipt_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.goods_receipt_items (
    id integer NOT NULL,
    grn_id integer NOT NULL,
    po_item_id integer NOT NULL,
    received_qty integer NOT NULL,
    batch_number character varying(60),
    expiry_date date,
    CONSTRAINT check_goods_receipt_item_qty_positive CHECK ((received_qty > 0))
);


ALTER TABLE public.goods_receipt_items OWNER TO postgres;

--
-- Name: goods_receipt_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.goods_receipt_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.goods_receipt_items_id_seq OWNER TO postgres;

--
-- Name: goods_receipt_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.goods_receipt_items_id_seq OWNED BY public.goods_receipt_items.id;


--
-- Name: goods_receipts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.goods_receipts (
    id integer NOT NULL,
    po_id integer NOT NULL,
    received_by integer,
    received_date date NOT NULL,
    notes text,
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.goods_receipts OWNER TO postgres;

--
-- Name: goods_receipts_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.goods_receipts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.goods_receipts_id_seq OWNER TO postgres;

--
-- Name: goods_receipts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.goods_receipts_id_seq OWNED BY public.goods_receipts.id;


--
-- Name: inventory_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.inventory_logs (
    id integer NOT NULL,
    product_id integer NOT NULL,
    old_stock integer NOT NULL,
    new_stock integer NOT NULL,
    changed_by integer,
    reason character varying(255) NOT NULL,
    reference integer,
    "timestamp" timestamp without time zone NOT NULL
);


ALTER TABLE public.inventory_logs OWNER TO postgres;

--
-- Name: inventory_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.inventory_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.inventory_logs_id_seq OWNER TO postgres;

--
-- Name: inventory_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.inventory_logs_id_seq OWNED BY public.inventory_logs.id;


--
-- Name: invoice_sequences; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.invoice_sequences (
    year integer NOT NULL,
    last_seq integer NOT NULL
);


ALTER TABLE public.invoice_sequences OWNER TO postgres;

--
-- Name: invoice_sequences_year_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.invoice_sequences_year_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.invoice_sequences_year_seq OWNER TO postgres;

--
-- Name: invoice_sequences_year_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.invoice_sequences_year_seq OWNED BY public.invoice_sequences.year;


--
-- Name: product_batches; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.product_batches (
    id integer NOT NULL,
    product_id integer NOT NULL,
    batch_number character varying(60) NOT NULL,
    expiry_date date,
    quantity integer NOT NULL,
    cost_price numeric(10,2),
    created_at timestamp without time zone NOT NULL,
    CONSTRAINT check_batch_qty_non_negative CHECK ((quantity >= 0))
);


ALTER TABLE public.product_batches OWNER TO postgres;

--
-- Name: product_batches_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.product_batches_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.product_batches_id_seq OWNER TO postgres;

--
-- Name: product_batches_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.product_batches_id_seq OWNED BY public.product_batches.id;


--
-- Name: product_variants; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.product_variants (
    id integer NOT NULL,
    product_id integer NOT NULL,
    size character varying(10) NOT NULL,
    color character varying(50) NOT NULL,
    sku character varying(100),
    barcode character varying(100) NOT NULL,
    price numeric(10,2) NOT NULL,
    stock integer NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    CONSTRAINT check_variant_price_positive CHECK ((price > (0)::numeric)),
    CONSTRAINT check_variant_stock_non_negative CHECK ((stock >= 0))
);


ALTER TABLE public.product_variants OWNER TO postgres;

--
-- Name: product_variants_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.product_variants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.product_variants_id_seq OWNER TO postgres;

--
-- Name: product_variants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.product_variants_id_seq OWNED BY public.product_variants.id;


--
-- Name: products; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.products (
    id integer NOT NULL,
    name character varying(200) NOT NULL,
    barcode character varying(100) NOT NULL,
    brand character varying(100),
    category character varying(100),
    description text,
    gst_percent integer NOT NULL,
    is_active boolean NOT NULL,
    is_weighed boolean NOT NULL,
    price_per_kg numeric(10,2),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    stock integer NOT NULL,
    price numeric(10,2) NOT NULL,
    CONSTRAINT check_gst_valid CHECK (((gst_percent >= 0) AND (gst_percent <= 28)))
);


ALTER TABLE public.products OWNER TO postgres;

--
-- Name: products_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.products_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.products_id_seq OWNER TO postgres;

--
-- Name: products_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.products_id_seq OWNED BY public.products.id;


--
-- Name: promotions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.promotions (
    id integer NOT NULL,
    name character varying(200) NOT NULL,
    promo_type character varying(30) NOT NULL,
    params text NOT NULL,
    start_date date,
    end_date date,
    is_active boolean NOT NULL,
    max_uses integer,
    current_uses integer NOT NULL,
    stackable boolean NOT NULL,
    created_by integer,
    created_at timestamp without time zone NOT NULL,
    CONSTRAINT check_promotion_current_uses_non_negative CHECK ((current_uses >= 0)),
    CONSTRAINT check_promotion_max_uses_positive CHECK (((max_uses IS NULL) OR (max_uses > 0)))
);


ALTER TABLE public.promotions OWNER TO postgres;

--
-- Name: promotions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.promotions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.promotions_id_seq OWNER TO postgres;

--
-- Name: promotions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.promotions_id_seq OWNED BY public.promotions.id;


--
-- Name: purchase_order_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.purchase_order_items (
    id integer NOT NULL,
    po_id integer NOT NULL,
    product_id integer NOT NULL,
    ordered_qty integer NOT NULL,
    unit_cost numeric(10,2),
    CONSTRAINT check_purchase_order_item_qty_positive CHECK ((ordered_qty > 0)),
    CONSTRAINT check_purchase_order_item_unit_cost_non_negative CHECK (((unit_cost IS NULL) OR (unit_cost >= (0)::numeric)))
);


ALTER TABLE public.purchase_order_items OWNER TO postgres;

--
-- Name: purchase_order_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.purchase_order_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.purchase_order_items_id_seq OWNER TO postgres;

--
-- Name: purchase_order_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.purchase_order_items_id_seq OWNED BY public.purchase_order_items.id;


--
-- Name: purchase_orders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.purchase_orders (
    id integer NOT NULL,
    supplier_id integer NOT NULL,
    status public.postatus NOT NULL,
    created_by integer,
    expected_date date,
    notes text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


ALTER TABLE public.purchase_orders OWNER TO postgres;

--
-- Name: purchase_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.purchase_orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.purchase_orders_id_seq OWNER TO postgres;

--
-- Name: purchase_orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.purchase_orders_id_seq OWNED BY public.purchase_orders.id;


--
-- Name: return_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.return_items (
    id integer NOT NULL,
    return_id integer NOT NULL,
    sale_item_id integer NOT NULL,
    product_id integer NOT NULL,
    quantity integer NOT NULL,
    refund_amount numeric(12,2) NOT NULL,
    reason character varying(100),
    CONSTRAINT check_return_item_quantity_positive CHECK ((quantity > 0)),
    CONSTRAINT check_return_item_refund_amount_non_negative CHECK ((refund_amount >= (0)::numeric))
);


ALTER TABLE public.return_items OWNER TO postgres;

--
-- Name: return_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.return_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.return_items_id_seq OWNER TO postgres;

--
-- Name: return_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.return_items_id_seq OWNED BY public.return_items.id;


--
-- Name: returns; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.returns (
    id integer NOT NULL,
    sale_id integer NOT NULL,
    processed_by integer NOT NULL,
    refund_method character varying(20) NOT NULL,
    total_refunded numeric(12,2) NOT NULL,
    note text,
    created_at timestamp without time zone NOT NULL,
    CONSTRAINT check_return_total_refunded_non_negative CHECK ((total_refunded >= (0)::numeric))
);


ALTER TABLE public.returns OWNER TO postgres;

--
-- Name: returns_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.returns_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.returns_id_seq OWNER TO postgres;

--
-- Name: returns_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.returns_id_seq OWNED BY public.returns.id;


--
-- Name: sale_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sale_items (
    id integer NOT NULL,
    sale_id integer NOT NULL,
    variant_id integer NOT NULL,
    quantity integer NOT NULL,
    price_at_sale numeric(10,2) NOT NULL,
    snapshot_size character varying(10) NOT NULL,
    snapshot_color character varying(50) NOT NULL,
    gst_percent integer NOT NULL,
    subtotal numeric(12,2) NOT NULL,
    weight_kg numeric(8,3),
    unit_label character varying(10),
    CONSTRAINT check_sale_item_quantity_positive CHECK ((quantity > 0)),
    CONSTRAINT check_sale_item_subtotal_non_negative CHECK ((subtotal >= (0)::numeric))
);


ALTER TABLE public.sale_items OWNER TO postgres;

--
-- Name: sale_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.sale_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sale_items_id_seq OWNER TO postgres;

--
-- Name: sale_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.sale_items_id_seq OWNED BY public.sale_items.id;


--
-- Name: sale_payments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sale_payments (
    id integer NOT NULL,
    sale_id integer NOT NULL,
    payment_method character varying(20) NOT NULL,
    amount numeric(12,2) NOT NULL,
    reference character varying(100),
    CONSTRAINT check_sale_payment_amount_non_negative CHECK ((amount >= (0)::numeric))
);


ALTER TABLE public.sale_payments OWNER TO postgres;

--
-- Name: sale_payments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.sale_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sale_payments_id_seq OWNER TO postgres;

--
-- Name: sale_payments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.sale_payments_id_seq OWNED BY public.sale_payments.id;


--
-- Name: sales; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sales (
    id integer NOT NULL,
    invoice_number character varying(20) NOT NULL,
    cashier_id integer NOT NULL,
    customer_id integer,
    total_amount numeric(12,2) NOT NULL,
    discount_percent numeric(5,2) NOT NULL,
    discount_amount numeric(12,2) NOT NULL,
    gst_total numeric(12,2) NOT NULL,
    grand_total numeric(10,2),
    payment_method character varying(20) NOT NULL,
    print_html text,
    is_printed boolean,
    created_at timestamp without time zone NOT NULL,
    CONSTRAINT check_sale_discount_amount_non_negative CHECK ((discount_amount >= (0)::numeric)),
    CONSTRAINT check_sale_discount_percent_range CHECK (((discount_percent >= (0)::numeric) AND (discount_percent <= (100)::numeric))),
    CONSTRAINT check_sale_grand_total_non_negative CHECK (((grand_total IS NULL) OR (grand_total >= (0)::numeric))),
    CONSTRAINT check_sale_gst_total_non_negative CHECK ((gst_total >= (0)::numeric)),
    CONSTRAINT check_sale_total_amount_non_negative CHECK ((total_amount >= (0)::numeric))
);


ALTER TABLE public.sales OWNER TO postgres;

--
-- Name: sales_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.sales_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sales_id_seq OWNER TO postgres;

--
-- Name: sales_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.sales_id_seq OWNED BY public.sales.id;


--
-- Name: suppliers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.suppliers (
    id integer NOT NULL,
    name character varying(200) NOT NULL,
    contact character varying(200),
    gst_no character varying(20),
    address text,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


ALTER TABLE public.suppliers OWNER TO postgres;

--
-- Name: suppliers_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.suppliers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.suppliers_id_seq OWNER TO postgres;

--
-- Name: suppliers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.suppliers_id_seq OWNED BY public.suppliers.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    username character varying(64) NOT NULL,
    password_hash character varying(256) NOT NULL,
    role public.roleenum NOT NULL,
    created_at timestamp without time zone NOT NULL,
    is_active boolean DEFAULT true NOT NULL
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: applied_promotions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.applied_promotions ALTER COLUMN id SET DEFAULT nextval('public.applied_promotions_id_seq'::regclass);


--
-- Name: cash_sessions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cash_sessions ALTER COLUMN id SET DEFAULT nextval('public.cash_sessions_id_seq'::regclass);


--
-- Name: customers id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customers ALTER COLUMN id SET DEFAULT nextval('public.customers_id_seq'::regclass);


--
-- Name: gift_cards id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gift_cards ALTER COLUMN id SET DEFAULT nextval('public.gift_cards_id_seq'::regclass);


--
-- Name: goods_receipt_items id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.goods_receipt_items ALTER COLUMN id SET DEFAULT nextval('public.goods_receipt_items_id_seq'::regclass);


--
-- Name: goods_receipts id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.goods_receipts ALTER COLUMN id SET DEFAULT nextval('public.goods_receipts_id_seq'::regclass);


--
-- Name: inventory_logs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_logs ALTER COLUMN id SET DEFAULT nextval('public.inventory_logs_id_seq'::regclass);


--
-- Name: invoice_sequences year; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.invoice_sequences ALTER COLUMN year SET DEFAULT nextval('public.invoice_sequences_year_seq'::regclass);


--
-- Name: product_batches id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.product_batches ALTER COLUMN id SET DEFAULT nextval('public.product_batches_id_seq'::regclass);


--
-- Name: product_variants id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.product_variants ALTER COLUMN id SET DEFAULT nextval('public.product_variants_id_seq'::regclass);


--
-- Name: products id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.products ALTER COLUMN id SET DEFAULT nextval('public.products_id_seq'::regclass);


--
-- Name: promotions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.promotions ALTER COLUMN id SET DEFAULT nextval('public.promotions_id_seq'::regclass);


--
-- Name: purchase_order_items id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_order_items ALTER COLUMN id SET DEFAULT nextval('public.purchase_order_items_id_seq'::regclass);


--
-- Name: purchase_orders id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_orders ALTER COLUMN id SET DEFAULT nextval('public.purchase_orders_id_seq'::regclass);


--
-- Name: return_items id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.return_items ALTER COLUMN id SET DEFAULT nextval('public.return_items_id_seq'::regclass);


--
-- Name: returns id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.returns ALTER COLUMN id SET DEFAULT nextval('public.returns_id_seq'::regclass);


--
-- Name: sale_items id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sale_items ALTER COLUMN id SET DEFAULT nextval('public.sale_items_id_seq'::regclass);


--
-- Name: sale_payments id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sale_payments ALTER COLUMN id SET DEFAULT nextval('public.sale_payments_id_seq'::regclass);


--
-- Name: sales id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales ALTER COLUMN id SET DEFAULT nextval('public.sales_id_seq'::regclass);


--
-- Name: suppliers id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.suppliers ALTER COLUMN id SET DEFAULT nextval('public.suppliers_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: applied_promotions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.applied_promotions (id, sale_id, promotion_id, promo_name, discount_amount, description) FROM stdin;
\.


--
-- Data for Name: cash_sessions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cash_sessions (id, cashier_id, opening_cash, system_total, closing_cash, start_time, end_time) FROM stdin;
1	1	50000.00	0.00	\N	2026-02-22 12:00:02.549172	\N
\.


--
-- Data for Name: customers; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.customers (id, name, phone, email, points, created_at, is_active) FROM stdin;
1	Test Customer	9876543210	\N	0	2026-02-22 11:55:16.304979	t
\.


--
-- Data for Name: gift_cards; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.gift_cards (id, code, initial_balance, balance, created_at, is_active) FROM stdin;
\.


--
-- Data for Name: goods_receipt_items; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.goods_receipt_items (id, grn_id, po_item_id, received_qty, batch_number, expiry_date) FROM stdin;
\.


--
-- Data for Name: goods_receipts; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.goods_receipts (id, po_id, received_by, received_date, notes, created_at) FROM stdin;
\.


--
-- Data for Name: inventory_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.inventory_logs (id, product_id, old_stock, new_stock, changed_by, reason, reference, "timestamp") FROM stdin;
\.


--
-- Data for Name: invoice_sequences; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.invoice_sequences (year, last_seq) FROM stdin;
\.


--
-- Data for Name: product_batches; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.product_batches (id, product_id, batch_number, expiry_date, quantity, cost_price, created_at) FROM stdin;
\.


--
-- Data for Name: product_variants; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.product_variants (id, product_id, size, color, sku, barcode, price, stock, is_active, created_at) FROM stdin;
\.


--
-- Data for Name: products; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.products (id, name, barcode, brand, category, description, gst_percent, is_active, is_weighed, price_per_kg, created_at, updated_at, stock, price) FROM stdin;
\.


--
-- Data for Name: promotions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.promotions (id, name, promo_type, params, start_date, end_date, is_active, max_uses, current_uses, stackable, created_by, created_at) FROM stdin;
\.


--
-- Data for Name: purchase_order_items; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.purchase_order_items (id, po_id, product_id, ordered_qty, unit_cost) FROM stdin;
\.


--
-- Data for Name: purchase_orders; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.purchase_orders (id, supplier_id, status, created_by, expected_date, notes, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: return_items; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.return_items (id, return_id, sale_item_id, product_id, quantity, refund_amount, reason) FROM stdin;
\.


--
-- Data for Name: returns; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.returns (id, sale_id, processed_by, refund_method, total_refunded, note, created_at) FROM stdin;
\.


--
-- Data for Name: sale_items; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sale_items (id, sale_id, variant_id, quantity, price_at_sale, snapshot_size, snapshot_color, gst_percent, subtotal, weight_kg, unit_label) FROM stdin;
\.


--
-- Data for Name: sale_payments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sale_payments (id, sale_id, payment_method, amount, reference) FROM stdin;
\.


--
-- Data for Name: sales; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sales (id, invoice_number, cashier_id, customer_id, total_amount, discount_percent, discount_amount, gst_total, grand_total, payment_method, print_html, is_printed, created_at) FROM stdin;
\.


--
-- Data for Name: suppliers; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.suppliers (id, name, contact, gst_no, address, is_active, created_at) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, name, username, password_hash, role, created_at, is_active) FROM stdin;
1	Administrator	admin	scrypt:32768:8:1$mdtZVnT0Sks1K0nm$19e37463f9a1bed16dbf25ade9931cacd9d7eb635364dc5b86433766987e002bf24129473ca135a189cda7e01c30fb2da2eb7aaee8d70bf3f2d9f21de7d5fe7a	admin	2026-02-22 11:19:37.296971	t
2	Standard Cashier	cashier	scrypt:32768:8:1$yEgn1f8xkRN35P84$99d45987a412075c4fdb2c41f0f59bd658c36c4d0f9b94809f16fc9306557a0187cc90de02aa42a27103cd3445e928bad957b1ea780578b50584aa989476fea7	cashier	2026-02-22 11:19:37.448136	t
\.


--
-- Name: applied_promotions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.applied_promotions_id_seq', 1, false);


--
-- Name: cash_sessions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.cash_sessions_id_seq', 1, true);


--
-- Name: customers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.customers_id_seq', 1, true);


--
-- Name: gift_cards_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gift_cards_id_seq', 1, false);


--
-- Name: goods_receipt_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.goods_receipt_items_id_seq', 1, false);


--
-- Name: goods_receipts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.goods_receipts_id_seq', 1, false);


--
-- Name: inventory_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.inventory_logs_id_seq', 1, false);


--
-- Name: invoice_sequences_year_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.invoice_sequences_year_seq', 1, false);


--
-- Name: product_batches_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.product_batches_id_seq', 1, false);


--
-- Name: product_variants_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.product_variants_id_seq', 1, false);


--
-- Name: products_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.products_id_seq', 1, false);


--
-- Name: promotions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.promotions_id_seq', 1, false);


--
-- Name: purchase_order_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.purchase_order_items_id_seq', 1, false);


--
-- Name: purchase_orders_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.purchase_orders_id_seq', 1, false);


--
-- Name: return_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.return_items_id_seq', 1, false);


--
-- Name: returns_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.returns_id_seq', 1, false);


--
-- Name: sale_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sale_items_id_seq', 1, false);


--
-- Name: sale_payments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sale_payments_id_seq', 1, false);


--
-- Name: sales_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sales_id_seq', 1, false);


--
-- Name: suppliers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.suppliers_id_seq', 1, false);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_id_seq', 2, true);


--
-- Name: applied_promotions applied_promotions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.applied_promotions
    ADD CONSTRAINT applied_promotions_pkey PRIMARY KEY (id);


--
-- Name: cash_sessions cash_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cash_sessions
    ADD CONSTRAINT cash_sessions_pkey PRIMARY KEY (id);


--
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- Name: gift_cards gift_cards_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gift_cards
    ADD CONSTRAINT gift_cards_pkey PRIMARY KEY (id);


--
-- Name: goods_receipt_items goods_receipt_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.goods_receipt_items
    ADD CONSTRAINT goods_receipt_items_pkey PRIMARY KEY (id);


--
-- Name: goods_receipts goods_receipts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.goods_receipts
    ADD CONSTRAINT goods_receipts_pkey PRIMARY KEY (id);


--
-- Name: inventory_logs inventory_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_logs
    ADD CONSTRAINT inventory_logs_pkey PRIMARY KEY (id);


--
-- Name: invoice_sequences invoice_sequences_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.invoice_sequences
    ADD CONSTRAINT invoice_sequences_pkey PRIMARY KEY (year);


--
-- Name: product_batches product_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.product_batches
    ADD CONSTRAINT product_batches_pkey PRIMARY KEY (id);


--
-- Name: product_variants product_variants_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.product_variants
    ADD CONSTRAINT product_variants_pkey PRIMARY KEY (id);


--
-- Name: products products_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);


--
-- Name: promotions promotions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.promotions
    ADD CONSTRAINT promotions_pkey PRIMARY KEY (id);


--
-- Name: purchase_order_items purchase_order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_pkey PRIMARY KEY (id);


--
-- Name: purchase_orders purchase_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_pkey PRIMARY KEY (id);


--
-- Name: return_items return_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.return_items
    ADD CONSTRAINT return_items_pkey PRIMARY KEY (id);


--
-- Name: returns returns_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.returns
    ADD CONSTRAINT returns_pkey PRIMARY KEY (id);


--
-- Name: sale_items sale_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sale_items
    ADD CONSTRAINT sale_items_pkey PRIMARY KEY (id);


--
-- Name: sale_payments sale_payments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sale_payments
    ADD CONSTRAINT sale_payments_pkey PRIMARY KEY (id);


--
-- Name: sales sales_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales
    ADD CONSTRAINT sales_pkey PRIMARY KEY (id);


--
-- Name: suppliers suppliers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_applied_promotions_sale_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_applied_promotions_sale_id ON public.applied_promotions USING btree (sale_id);


--
-- Name: ix_customers_phone; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_customers_phone ON public.customers USING btree (phone);


--
-- Name: ix_gift_cards_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_gift_cards_code ON public.gift_cards USING btree (code);


--
-- Name: ix_goods_receipt_items_grn_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_goods_receipt_items_grn_id ON public.goods_receipt_items USING btree (grn_id);


--
-- Name: ix_goods_receipts_po_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_goods_receipts_po_id ON public.goods_receipts USING btree (po_id);


--
-- Name: ix_inventory_logs_reference; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_inventory_logs_reference ON public.inventory_logs USING btree (reference);


--
-- Name: ix_inventory_logs_timestamp; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_inventory_logs_timestamp ON public.inventory_logs USING btree ("timestamp");


--
-- Name: ix_product_batches_product_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_product_batches_product_id ON public.product_batches USING btree (product_id);


--
-- Name: ix_product_variants_barcode; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_product_variants_barcode ON public.product_variants USING btree (barcode);


--
-- Name: ix_product_variants_is_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_product_variants_is_active ON public.product_variants USING btree (is_active);


--
-- Name: ix_product_variants_product_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_product_variants_product_id ON public.product_variants USING btree (product_id);


--
-- Name: ix_products_barcode; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_products_barcode ON public.products USING btree (barcode);


--
-- Name: ix_products_is_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_products_is_active ON public.products USING btree (is_active);


--
-- Name: ix_products_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_products_name ON public.products USING btree (name);


--
-- Name: ix_purchase_order_items_po_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_purchase_order_items_po_id ON public.purchase_order_items USING btree (po_id);


--
-- Name: ix_purchase_orders_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_purchase_orders_status ON public.purchase_orders USING btree (status);


--
-- Name: ix_purchase_orders_supplier_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_purchase_orders_supplier_id ON public.purchase_orders USING btree (supplier_id);


--
-- Name: ix_sale_items_variant_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_sale_items_variant_id ON public.sale_items USING btree (variant_id);


--
-- Name: ix_sales_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_sales_created_at ON public.sales USING btree (created_at);


--
-- Name: ix_sales_invoice_number; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_sales_invoice_number ON public.sales USING btree (invoice_number);


--
-- Name: ix_suppliers_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_suppliers_name ON public.suppliers USING btree (name);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: applied_promotions applied_promotions_promotion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.applied_promotions
    ADD CONSTRAINT applied_promotions_promotion_id_fkey FOREIGN KEY (promotion_id) REFERENCES public.promotions(id);


--
-- Name: applied_promotions applied_promotions_sale_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.applied_promotions
    ADD CONSTRAINT applied_promotions_sale_id_fkey FOREIGN KEY (sale_id) REFERENCES public.sales(id);


--
-- Name: cash_sessions cash_sessions_cashier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cash_sessions
    ADD CONSTRAINT cash_sessions_cashier_id_fkey FOREIGN KEY (cashier_id) REFERENCES public.users(id);


--
-- Name: goods_receipt_items goods_receipt_items_grn_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.goods_receipt_items
    ADD CONSTRAINT goods_receipt_items_grn_id_fkey FOREIGN KEY (grn_id) REFERENCES public.goods_receipts(id) ON DELETE CASCADE;


--
-- Name: goods_receipt_items goods_receipt_items_po_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.goods_receipt_items
    ADD CONSTRAINT goods_receipt_items_po_item_id_fkey FOREIGN KEY (po_item_id) REFERENCES public.purchase_order_items(id);


--
-- Name: goods_receipts goods_receipts_po_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.goods_receipts
    ADD CONSTRAINT goods_receipts_po_id_fkey FOREIGN KEY (po_id) REFERENCES public.purchase_orders(id);


--
-- Name: goods_receipts goods_receipts_received_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.goods_receipts
    ADD CONSTRAINT goods_receipts_received_by_fkey FOREIGN KEY (received_by) REFERENCES public.users(id);


--
-- Name: inventory_logs inventory_logs_changed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_logs
    ADD CONSTRAINT inventory_logs_changed_by_fkey FOREIGN KEY (changed_by) REFERENCES public.users(id);


--
-- Name: inventory_logs inventory_logs_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_logs
    ADD CONSTRAINT inventory_logs_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);


--
-- Name: product_batches product_batches_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.product_batches
    ADD CONSTRAINT product_batches_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: product_variants product_variants_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.product_variants
    ADD CONSTRAINT product_variants_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: promotions promotions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.promotions
    ADD CONSTRAINT promotions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: purchase_order_items purchase_order_items_po_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_po_id_fkey FOREIGN KEY (po_id) REFERENCES public.purchase_orders(id) ON DELETE CASCADE;


--
-- Name: purchase_order_items purchase_order_items_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);


--
-- Name: purchase_orders purchase_orders_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: purchase_orders purchase_orders_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id);


--
-- Name: return_items return_items_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.return_items
    ADD CONSTRAINT return_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);


--
-- Name: return_items return_items_return_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.return_items
    ADD CONSTRAINT return_items_return_id_fkey FOREIGN KEY (return_id) REFERENCES public.returns(id);


--
-- Name: return_items return_items_sale_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.return_items
    ADD CONSTRAINT return_items_sale_item_id_fkey FOREIGN KEY (sale_item_id) REFERENCES public.sale_items(id);


--
-- Name: returns returns_processed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.returns
    ADD CONSTRAINT returns_processed_by_fkey FOREIGN KEY (processed_by) REFERENCES public.users(id);


--
-- Name: returns returns_sale_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.returns
    ADD CONSTRAINT returns_sale_id_fkey FOREIGN KEY (sale_id) REFERENCES public.sales(id);


--
-- Name: sale_items sale_items_sale_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sale_items
    ADD CONSTRAINT sale_items_sale_id_fkey FOREIGN KEY (sale_id) REFERENCES public.sales(id);


--
-- Name: sale_items sale_items_variant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sale_items
    ADD CONSTRAINT sale_items_variant_id_fkey FOREIGN KEY (variant_id) REFERENCES public.product_variants(id);


--
-- Name: sale_payments sale_payments_sale_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sale_payments
    ADD CONSTRAINT sale_payments_sale_id_fkey FOREIGN KEY (sale_id) REFERENCES public.sales(id);


--
-- Name: sales sales_cashier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales
    ADD CONSTRAINT sales_cashier_id_fkey FOREIGN KEY (cashier_id) REFERENCES public.users(id);


--
-- Name: sales sales_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales
    ADD CONSTRAINT sales_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- PostgreSQL database dump complete
--

\unrestrict Rr7ubW39EMJXrdke2vRgkdC7AIuV7Ea3wqL7o6byKeqkRcpkeibkBJ4H8ah4bAD

