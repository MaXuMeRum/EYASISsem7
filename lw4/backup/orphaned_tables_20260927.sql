--
-- PostgreSQL database dump
--

\restrict j4V3bM8fBCMa0e53E0RXDpbEnm8tzZnhESu6SdYua7TozStEm2R0BO66Rbhjd9S

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: documents; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.documents (
    id integer NOT NULL,
    title character varying(255),
    author character varying(255),
    year integer,
    type character varying(100),
    text text,
    filename character varying(255)
);


ALTER TABLE public.documents OWNER TO postgres;

--
-- Name: documents_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.documents_id_seq OWNER TO postgres;

--
-- Name: documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.documents_id_seq OWNED BY public.documents.id;


--
-- Name: sentences; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sentences (
    id integer NOT NULL,
    doc_id integer,
    sentence_index integer,
    text text
);


ALTER TABLE public.sentences OWNER TO postgres;

--
-- Name: sentences_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.sentences_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sentences_id_seq OWNER TO postgres;

--
-- Name: sentences_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.sentences_id_seq OWNED BY public.sentences.id;


--
-- Name: tokens; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.tokens (
    id integer NOT NULL,
    sentence_id integer,
    doc_id integer,
    token_index integer,
    wordform character varying(100),
    lemma character varying(100),
    pos_rus character varying(50),
    morph_rus text
);


ALTER TABLE public.tokens OWNER TO postgres;

--
-- Name: tokens_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.tokens_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.tokens_id_seq OWNER TO postgres;

--
-- Name: tokens_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.tokens_id_seq OWNED BY public.tokens.id;


--
-- Name: translation_sessions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.translation_sessions (
    id integer NOT NULL,
    source_lang character varying(10),
    target_lang character varying(10),
    source_text text,
    translated_text text,
    total_words integer,
    translated_words integer,
    unknown_words text,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.translation_sessions OWNER TO postgres;

--
-- Name: translation_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.translation_sessions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.translation_sessions_id_seq OWNER TO postgres;

--
-- Name: translation_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.translation_sessions_id_seq OWNED BY public.translation_sessions.id;


--
-- Name: documents id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.documents ALTER COLUMN id SET DEFAULT nextval('public.documents_id_seq'::regclass);


--
-- Name: sentences id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sentences ALTER COLUMN id SET DEFAULT nextval('public.sentences_id_seq'::regclass);


--
-- Name: tokens id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tokens ALTER COLUMN id SET DEFAULT nextval('public.tokens_id_seq'::regclass);


--
-- Name: translation_sessions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.translation_sessions ALTER COLUMN id SET DEFAULT nextval('public.translation_sessions_id_seq'::regclass);


--
-- Data for Name: documents; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.documents (id, title, author, year, type, text, filename) FROM stdin;
\.


--
-- Data for Name: sentences; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sentences (id, doc_id, sentence_index, text) FROM stdin;
\.


--
-- Data for Name: tokens; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.tokens (id, sentence_id, doc_id, token_index, wordform, lemma, pos_rus, morph_rus) FROM stdin;
\.


--
-- Data for Name: translation_sessions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.translation_sessions (id, source_lang, target_lang, source_text, translated_text, total_words, translated_words, unknown_words, created_at) FROM stdin;
1	en	ru	Machine translation is a subfield of computational linguistics. The system analyzes the source sentence and produces a translation.	Machine translation subfield computational linguistics system analyzes source sentence and produces translation	18	0	["Machine", "translation", "subfield", "computational", "linguistics", "system", "analyzes", "source", "sentence", "and", "produces", "translation"]	2026-09-27 18:39:20.774073
\.


--
-- Name: documents_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.documents_id_seq', 1, false);


--
-- Name: sentences_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sentences_id_seq', 1, false);


--
-- Name: tokens_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.tokens_id_seq', 1, false);


--
-- Name: translation_sessions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.translation_sessions_id_seq', 1, true);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: sentences sentences_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sentences
    ADD CONSTRAINT sentences_pkey PRIMARY KEY (id);


--
-- Name: tokens tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tokens
    ADD CONSTRAINT tokens_pkey PRIMARY KEY (id);


--
-- Name: translation_sessions translation_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.translation_sessions
    ADD CONSTRAINT translation_sessions_pkey PRIMARY KEY (id);


--
-- PostgreSQL database dump complete
--

\unrestrict j4V3bM8fBCMa0e53E0RXDpbEnm8tzZnhESu6SdYua7TozStEm2R0BO66Rbhjd9S

