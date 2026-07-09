--
-- PostgreSQL database dump
--

\restrict XT1uYYELKRVubrQ6d4yVYWWqd3AFVx7on1NnLDOCNs1JGbl1GDEVHqiGKkAeIRx

-- Dumped from database version 16.11
-- Dumped by pg_dump version 16.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
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
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    name character varying(100) NOT NULL,
    phone character varying(20),
    avatar_url character varying(500),
    role character varying(50) NOT NULL,
    permissions character varying[],
    last_login character varying(50),
    notes text,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    google_id character varying(100),
    condominio_id uuid,
    employee_id uuid
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (email, password_hash, name, phone, avatar_url, role, permissions, last_login, notes, id, created_at, updated_at, is_active, google_id, condominio_id, employee_id) FROM stdin;
opaiva@conectamais.pro	$2b$12$5JVcriA8LMaXjGehnPPrCOdhWP1gbnB/E.iOmw5YL4TsBa2MZ.YnK	Orlailson Paiva	\N	\N	admin	{module:dp,module:operacional,module:ged}	2026-01-26T01:31:34.719810	\N	8fb890bb-a2d3-42dd-aa2b-b483fa8afa2f	2026-01-22 18:57:57.916305+00	2026-01-26 01:31:34.44033+00	t	\N	\N	\N
avieira@conectamais.pro	$2b$12$0dz7k4cAHWxVZCXEwIyUMuHkOehMmpYuPm/1Dxd1nNcDOHiPhZPmm	Antonio Carlos Vieira	\N	\N	agente	\N	2026-01-22T19:13:02.946789	\N	b3a028ac-6f02-41cb-aed4-581bd148dcc0	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:02.65213+00	t	\N	\N	\N
adsantos@conectamais.pro	$2b$12$FStNxfq75754VHGd1/TB4eMep.kl3CMowBrsAzjEhlAF7kIj1lNfO	Antonio Diniz Assis Dos Santos	\N	\N	agente	\N	2026-01-22T19:13:03.568808	\N	4ffa4842-fbb6-427e-931e-fa649ca2ed05	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:03.2766+00	t	\N	\N	\N
awsilva@conectamais.pro	$2b$12$G1kPOJazmCaIXJ2K2R4WLeeGZKSifpqqDCyBB2sIZhksWU05qdzca	Antonio Walcicley Pereira Da Silva	\N	\N	admin	\N	2026-01-27T17:23:27.938282	\N	cfbce61d-e8b2-4831-8cc4-3099acdb470f	2026-01-22 19:12:38.312218+00	2026-01-27 17:23:27.655861+00	t	\N	\N	29dae28f-e688-4df0-8879-2704d8351d87
josilva@conectamais.pro	$2b$12$MgeEPhs645HACxn/UpRVgOhE1mUlT86yq7MDeEl2XcVyaAWn9OmOK	Josiane De Sousa Silva	\N	\N	agente	\N	2026-01-22T20:46:48.673837	\N	0f3d498c-8a9f-41f7-abd9-1f6f451f2435	2026-01-22 19:12:38.312218+00	2026-01-22 20:46:48.429505+00	t	\N	\N	\N
gaparicio@conectamais.pro	$2b$12$sxrlFPPPvOdYLa/YJ1eQzenv5l0Hh0swH.dr.UzTYIL2xBUiqPDve	Gernanes Binda Aparicio	\N	\N	agente	\N	2026-01-22T19:13:03.940873	\N	5f640bb5-6b5a-4fda-972b-82a5e451cbb6	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:03.624859+00	t	\N	\N	\N
afigueira@conectamais.pro	$2b$12$rAFpMP2p4jVICOvpaYrf3Or821JO2eceXWEW5QzYWbteo3JWb6Ije	Aryelton Braga Figueira	\N	\N	agente	\N	2026-01-22T19:13:04.558259	\N	4a2af29e-3d8a-4845-bc2a-b6c37922ca4e	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:04.30404+00	t	\N	\N	\N
fmaciel@conectamais.pro	$2b$12$gOO7remTez6PX5lvkUREiOyTpM2edRixOlOPU2hL4Opz5cqmnxcfu	Fernanda Vinhote Maciel	\N	\N	agente	\N	2026-01-22T19:13:05.240536	\N	06b78d19-15a1-4be9-b84d-8a9477f9217c	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:04.945711+00	t	\N	\N	\N
aneves@conectamais.pro	$2b$12$6fBzUH4RNCWYl7OAD0cLzu350yzfLsAL.ZEC8Jdafk.f0naDSqEwW	Anilson Jose Seixas Neves	\N	\N	agente	\N	2026-01-22T19:13:07.259009	\N	78993fcf-e6a5-426f-a3e0-f790bf64d106	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:06.856125+00	t	\N	\N	\N
glima@conectamais.pro	$2b$12$1Zs.mC19ptbB1WeQCAJwFuFN2Bi609G9P46Zsz04DI8OVympdgQyC	Gelson Bernardo Lima	\N	\N	agente	\N	2026-01-22T19:13:07.735234	\N	610ebdbd-cbc7-4ece-a182-8e49bb9926d7	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:07.32169+00	t	\N	\N	\N
edsouza@conectamais.pro	$2b$12$anZ7McWPcD2vOFzeHK2rGOapANFha38HYDZTHJgoPxY.44WkqTare	Eduardo Oliveira De Souza	\N	\N	agente	\N	2026-01-22T19:13:08.837225	\N	223127bf-5fe2-43db-98a4-fefbb62241dc	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:08.504454+00	t	\N	\N	\N
aivasconcelos@conectamais.pro	$2b$12$J.JDjIU8cWt07.bM079kw.iGX3IRT3QAaXaN.TX1/uYyiWsnwlwYy	Ailton Cesar Vasconcelos	\N	\N	agente	\N	2026-01-22T19:13:09.161930	\N	18be91b1-30d0-466f-a4c0-6832075c201f	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:08.868364+00	t	\N	\N	\N
edsousa@conectamais.pro	$2b$12$UIKiQQtO6EHd/noF0ms2J.JgJWBlBxj8.wrgqogW9BjaEIzgHZYqO	Edilene Sales Sousa	\N	\N	agente	\N	2026-01-22T19:13:09.457734	\N	9752f38c-5084-4fd9-86bf-e22c498464f0	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:09.189468+00	t	\N	\N	\N
ecastro@conectamais.pro	$2b$12$L8.Lah6l88K6tw5UexMz3.C3mrQT1hUOMKnEroDZkrpoCuxe15qTS	Eidy Culier De Castro	\N	\N	agente	\N	2026-01-22T19:13:10.342569	\N	5114ea34-d214-4721-a471-ffb949e38237	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:10.101747+00	t	\N	\N	\N
agama@conectamais.pro	$2b$12$VgP8PBuvAPzPA/Catu6L4O/9U97sXcN9U7HklUdFqSKHOuc4ZiDbi	Antonio Carlos Castro Gama	\N	\N	agente	\N	2026-01-22T19:13:10.622064	\N	bf199e73-2e4d-48e4-8c81-c32ca06837f5	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:10.361265+00	t	\N	\N	\N
anvasconcelos@conectamais.pro	$2b$12$sHrpaeE.y8xCKHAUGJUgi.Q1mXTcLnIZ6XqGZfwImq7tjpIUr8js6	Andrew Costa Vasconcelos	\N	\N	agente	\N	2026-01-22T19:13:10.896460	\N	15eb19a7-0b04-463c-b580-35432e8dcdce	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:10.651032+00	t	\N	\N	\N
edominguez@conectamais.pro	$2b$12$/fTYCzTkBkeL1ZCiFr7lROgTTPuf6MrLp45axu4Qivt6H0eSTR/N6	Edward Jose Atencio Dominguez	\N	\N	agente	\N	2026-01-22T19:13:11.183183	\N	6be2b033-fc69-41bc-a397-db19c6a119c5	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:10.914798+00	t	\N	\N	\N
jpires@conectamais.pro	$2b$12$S18w5dLu.BSxFuoA.70fBeRziWK9QrSEZhqR5FFAvwpyEd2oKLmYK	Jordana Bacry Pires	\N	\N	agente	\N	2026-01-22T19:13:11.475882	\N	ef01826a-1c21-478f-9586-82bb2f4dbecb	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:11.202644+00	t	\N	\N	\N
afilho@conectamais.pro	$2b$12$/9tzbDTcuwTsIFQ7NHaNKO3n9oZfSielml5Kx.IBkmGYgs8xNpcpK	Ademir Salustiano De Souza Filho	\N	\N	agente	\N	2026-01-22T19:13:12.538067	\N	81aefc44-b650-4328-8edc-a7bf8438c432	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:12.296931+00	t	\N	\N	\N
clima@conectamais.pro	$2b$12$OlNXrgkoVC9P0U6BRmtKxOqrAwIH74m1tfC054JBZ7zskros2E9Xa	Carlos Alberto Assis De Lima	\N	\N	agente	\N	2026-01-22T19:13:12.802982	\N	e417d541-14b9-4794-944c-d49f9234bb7a	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:12.557426+00	t	\N	\N	\N
enunes@conectamais.pro	$2b$12$qDJhAX1L58dqINR0EQgLHeT0xiJrR5dw.kzqWOStkfQ0VFKoTMKuq	Elen Xavier Nunes	\N	\N	agente	\N	2026-01-22T19:13:13.079935	\N	29a7c879-de04-44a4-b5bf-53a04e5e6c1c	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:12.827916+00	t	\N	\N	\N
jbatista@conectamais.pro	$2b$12$SechwNY2rhtYEHzfecCoROzlZbmqUytklYIs26WAR.jnNm40MFIOW	Jefferson Da Silva Batista	\N	\N	agente	\N	2026-01-22T19:13:13.666080	\N	72e34e30-d775-441e-a7c4-4faebdb72cc4	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:13.386004+00	t	\N	\N	\N
jcsantos@conectamais.pro	$2b$12$vbAgxNp/fjZKQ8mZeicadOXIaDvE57ONpK8jesfHKpSRMUlOYU3Di	Julio Cesar Assis Santos	\N	\N	agente	\N	2026-01-22T19:13:14.211567	\N	2573ac80-ec96-49e5-b09b-af8e6ff8ee10	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:13.952339+00	t	\N	\N	\N
aalves@conectamais.pro	$2b$12$sl7CKjn78RmyAM.3ZWgDyuo9nsh.7.5wjEpUdMafC4KAeAGSgPDDW	Adailson Serra Alves	\N	\N	agente	\N	2026-01-22T19:13:14.497791	\N	b075c83f-e63c-46e8-bcfa-b3075716254f	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:14.254591+00	t	\N	\N	\N
frsouza@conectamais.pro	$2b$12$fyxPgaYUsIOV/BmhrkZUv.khMMiyQ57lZYMnfKI.sxBGVMQWo5VJK	Francisco Ramon Farias De Souza	\N	\N	agente	\N	2026-01-22T19:13:15.119471	\N	ff29f3f7-c4cc-4689-a8f8-5cdb61eb209a	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:14.800905+00	t	\N	\N	\N
csousa@conectamais.pro	$2b$12$DwZDNaaY2vi0I2KmCx1vN.G6LyzA6ra1GHWUofLSQchm4NSk9VxBm	Celiane Garcia De Sousa	\N	\N	agente	\N	2026-01-22T19:13:15.389630	\N	497e5b51-b8b4-4501-8fb3-8ac9343ecbbc	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:15.147758+00	t	\N	\N	\N
jaqsantos@conectamais.pro	$2b$12$5S9LMChaB081f32.3EhuBOq29VnrhyftgOnG4KfP1qL5H/pkOuUs2	Jaqueline Carlos Dos Santos	\N	\N	agente	\N	2026-01-22T19:13:15.666423	\N	828f3c1e-005f-4860-96a1-4af9f3849355	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:15.419468+00	t	\N	\N	\N
kpinto@conectamais.pro	$2b$12$qF2Q5GrzsxGZKeZpverwnusFVAJs0ZPJnCXyS2WUBOVMiLv8I95GG	Keyson Da Silva Pinto	\N	\N	agente	\N	2026-01-22T19:13:04.255529	\N	ec218780-2e06-40aa-a399-e9015b652730	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:03.980896+00	t	\N	\N	\N
rasilva@conectamais.pro	$2b$12$0FXt752siJhXx2fCK3tan.ehrGHg4Iw9vgpuvVtTMKEAiATdhmfG.	Raimundo Jose Batista Da Silva	\N	\N	agente	\N	2026-01-22T19:13:04.909743	\N	4faa8b42-667e-44a4-934c-05777a4e8029	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:04.578962+00	t	\N	\N	\N
tmeira@conectamais.pro	$2b$12$MzNQ9rMqETLHI35yQphMke68zUtgQzV68/sFZm/JL6ZzSeQoSV0te	Telma Maria Lages Meira	\N	\N	agente	\N	2026-01-22T19:13:05.642820	\N	ed2d4982-12c0-4068-bf08-949fc6f291b5	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:05.26716+00	t	\N	\N	\N
masilva@conectamais.pro	$2b$12$nVmiI4ojUDMiudcNkWGOVeCIe45MKOLPuitAy86ulz6.cBfBKNzE6	Marcelino Aurismar Da Silva	\N	\N	agente	\N	2026-01-22T19:13:05.970040	\N	48a5f80b-34c1-405c-90af-60d68caf83e7	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:05.666691+00	t	\N	\N	\N
wdias@conectamais.pro	$2b$12$5xt1dtOEy.B3Dq9Ol8C.u.qa2NDjLO1gB2FJ6clb7fMJ502IsNcDa	Wanderson Matos Dias	\N	\N	agente	\N	2026-01-22T19:13:06.309305	\N	50f6dae6-52f1-4f98-8734-ac8a0be60f2b	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:05.993393+00	t	\N	\N	\N
epereira@conectamais.pro	$2b$12$5huz/TtzPNML4CUGallIFuDVIk59YQhwfXK5lUMYLUzK8EqveFB4y	Erika Cristina Maquine Pereira	\N	\N	agente	\N	2026-01-22T19:13:03.242800	\N	9b9c5150-2aef-4e21-8d0e-3b6e2588a576	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:02.9692+00	t	\N	\N	6bf7804a-4976-44d2-aa3e-5bf1f25c3530
emarques@conectamais.pro	$2b$12$XRQSdRf2lMJlCuN9L7aLpeRpGDZ/oBJqvJaCN3bxqF7NW34rRJHo2	Ediwilson Correa Marques	\N	\N	agente	\N	2026-01-22T19:13:08.074518	\N	aaccd091-4bfd-4e8e-a324-44c04b20c314	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:07.767649+00	t	\N	\N	ebfc72fe-7081-47b8-bce6-88b81cdcb09a
rbatista@conectamais.pro	$2b$12$XWQVJ0qv828hA4KBcKownONxFp89vTdg0gvHxW2VLr/.CfmnxBPQW	Railson Coelho Batista	\N	\N	agente	\N	2026-01-22T19:13:06.796141	\N	23c32aa9-804e-4422-9a5f-d092d9c2a2f7	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:06.371537+00	t	\N	\N	\N
rfigueiredo@conectamais.pro	$2b$12$OlWAL6sAm3hCCn6tInjNP.GF3AnlEZLA5m.Dg74uAib5y/P7pRYbK	Ruan Rodrigues Figueiredo	\N	\N	agente	\N	2026-01-22T19:13:08.455887	\N	c9632b49-1a64-499d-affb-a1a274e656c1	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:08.12319+00	t	\N	\N	\N
rmenezes@conectamais.pro	$2b$12$nElCR2YCv/5.j87ulRiWdOOoeefxEjeX4G3N2UQg90TMI4E6EAHSK	Roberto Pereira Menezes	\N	\N	agente	\N	2026-01-22T19:13:09.716512	\N	5c7d2fcd-97e2-4028-8bd9-858919e24c4e	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:09.476803+00	t	\N	\N	\N
vasilva@conectamais.pro	$2b$12$z7NrN/gFeG0gPD.kfRQ.9.PRP3980JTxdVQwBgVeSYAeImbX3bgxy	Vanderlice Santos Da Silva	\N	\N	agente	\N	2026-01-22T19:13:10.084363	\N	a69f0982-bbb2-4da7-abce-11e023f9287d	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:09.746359+00	t	\N	\N	\N
kjesus@conectamais.pro	$2b$12$061zrpJW.Irx5Lb2Cf6H3eApav0vDTgTV91r7s8qjIhwcetIdzj2m	Kalel Silva De Jesus	\N	\N	agente	\N	2026-01-22T19:13:11.738526	\N	b2d7c151-78ec-4a9e-a279-c1fea037e30e	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:11.496891+00	t	\N	\N	\N
mchagas@conectamais.pro	$2b$12$IC4uiEspLVnZf3u3L8kwfOmy/9t531vVLoUHqujPfktTr8Rs61Fay	Mauricio Alves Chagas	\N	\N	agente	\N	2026-01-22T19:13:12.015238	\N	6e902d64-14e8-4e87-84fd-00253c0d1aec	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:11.762784+00	t	\N	\N	\N
tmatos@conectamais.pro	$2b$12$ZhaHQOxDumdLH8qbxp9Q5e8qHKvq3b4HdjsvhYU04.H3EuGuwLOnu	Thais Ferreira Matos	\N	\N	agente	\N	2026-01-22T19:13:12.276465	\N	3eabb8e4-26d4-43fc-8046-116453522bcc	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:12.030354+00	t	\N	\N	\N
mpinheiro@conectamais.pro	$2b$12$P6U7jTOThclZSoEZNn6Ou.P40xUuuwFiLV72vBEFYfNw3SDBfQqxu	Marta Da Silva Pinheiro	\N	\N	agente	\N	2026-01-22T19:13:13.365974	\N	b24a36f9-c271-4a87-bc04-1ab8ef6cb133	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:13.106903+00	t	\N	\N	\N
losilva@conectamais.pro	$2b$12$nGek567R2iZPiNXpyDN7qOttgvS9ODLQQG2Awz/krREvZC.xPSZ1K	Lorinaldo Oliveira Da Silva	\N	\N	agente	\N	2026-01-22T19:13:13.927975	\N	5cb0c5c1-6ff9-4cf3-ad05-ef5338adf2eb	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:13.680988+00	t	\N	\N	\N
ofilho@conectamais.pro	$2b$12$aJp/VizTPXNhAJ8AoRtrF.oJlRANXieD02mrMUMc9YyiMW9Lz/QFS	Oscar Soares Da Costa Filho	\N	\N	agente	\N	2026-01-22T19:13:14.768548	\N	4b468682-bbbc-4c15-9b24-f467fb911e6d	2026-01-22 19:12:38.312218+00	2026-01-22 19:13:14.525968+00	t	\N	\N	\N
test@admin.com	$2b$12$5JVcriA8LMaXjGehnPPrCOdhWP1gbnB/E.iOmw5YL4TsBa2MZ.YnK	Test Admin	\N	\N	admin	\N	2026-01-27T04:36:46.324108	\N	a0a0a0a0-1111-2222-3333-444444444444	2026-01-26 01:27:58.89771+00	2026-01-27 04:36:46.063874+00	t	\N	\N	\N
marcia@mbconsultoria.sst	$2b$12$dcoAhNHc0tZQGkPkiVUhHeQeYHvuJhKMuxl2hC1P4IHc99dXw5FCO	Marcia — MB Consultoria (SST)	\N	\N	operator	{module:dp,module:ged}	2026-07-07T23:37:47.459242	\N	d4e309e9-026c-4c81-94a9-8c2ba9e4f80e	2026-07-07 23:36:58.478827+00	2026-07-07 23:37:47.028989+00	t	\N	\N	\N
admin@conectaplus.com.br	$2b$12$1pDNbSGjp0LEjUidUFMPKu0LF4UpnVUTYZw.hd.WItQogj/.8kYeu	Administrador Teste	\N	\N	admin	\N	2026-03-11T04:04:21.464538	\N	b2c3d4e5-f6a7-8901-bcde-f12345678901	2026-01-23 17:54:04.303392+00	2026-03-11 04:04:21.221215+00	t	\N	\N	\N
epaiva@conectamais.pro	$2b$12$vIjDOJAhYcI71xmTD9u.Yefl7YGtlTFRCCvTjSBZBe5M5Zk9tYZEO	Orlailson Paiva	\N	\N	admin	{}	2026-02-15T18:39:27.059253	\N	54875585-3d4c-405c-858e-c5fbde316f8b	2026-01-28 14:48:14.991642+00	2026-02-15 18:39:26.806082+00	f	\N	\N	\N
jordansjesus@gmail.com	$2b$12$YFErPV6z2JsWeE8x2vSrnebVDQItxOM1hOrzG3bnPshx6yrC1BFmG	Jordan Jesus	\N	\N	operator	{}	2026-04-21T15:29:58.150809	\N	266007cb-02f9-4a88-8dbb-c47721dd0853	2026-01-17 01:34:32.908075+00	2026-04-21 15:29:58.149038+00	t	110802006554780362246	\N	\N
romondossantosaraujo16@gmail.com	$2b$12$TomVYRR4Alni5Cg9YO19mekIdSG/fy4LJyms3cqpLqupEUpItFBzC	Ramon Araujo	\N	\N	developer	{module:dp,module:operacional,module:crm,module:ged,module:dev}	2026-05-05T14:31:25.009370	\N	c3c0e5d7-1f6a-42d0-9d60-5c18d12a6d12	2026-05-05 14:04:19.413013+00	2026-05-05 14:31:24.753101+00	t	\N	\N	\N
loadtest@conectamais.pro	$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW	Load Test User	\N	\N	user	\N	\N	\N	c9327b0a-7558-4129-a164-7d80b6b3ba7a	2026-02-11 17:15:54.825772+00	2026-02-11 17:15:54.825772+00	t	\N	\N	\N
pjesus@conectamais.pro	$2b$12$Ee47e9YB8J9CfgbJy4nowe/20V7RYIoaSDylmiGaFIyFFH3UAohzy	Pyetra Jesus	\N	\N	admin	{all}	2026-05-05T16:24:17.945932	\N	1269276e-e34d-4e51-9bb9-df16fc648077	2026-05-05 14:04:06.220742+00	2026-05-05 16:24:17.652223+00	t	\N	\N	\N
jjesus@conectamais.pro	$2b$12$MNi9k8wLWiB8fMkugxTZluiEJ4C7lMKDXvqNutAh4dVmPObMfVMau	Jordan Jesus	\N	\N	admin	{all}	2026-07-08T18:37:36.153321	\N	ad9abb59-55fb-444e-a04f-0e1f22541de3	2026-01-16 23:52:20.487918+00	2026-07-08 18:37:35.878772+00	t	\N	a1b2c3d4-e5f6-7890-abcd-ef1234567890	\N
pedrodev@gmail.com	$2b$12$X2pcnCBI/3GACNWi.ywmSe2Y6.0GTFFmHf0ZdloWwj58pRmW92xAe	Pedro Rafael	\N	\N	admin	{}	2026-05-13T13:59:03.309652	\N	44c7f271-4405-4da9-8e98-a35658b9dd1a	2026-05-13 13:19:59.824503+00	2026-05-13 13:59:02.974828+00	t	\N	\N	\N
admin@conectamais.pro	$2b$12$Kli/PMx6QozcDIyhNalQT./dAh0MvTTG7iUEqlCLyErGIAQ48b8Py	Administrador	\N	\N	admin	\N	2026-04-13T03:42:29.097168	\N	20ee8641-962f-465d-ba7e-d2085c5f6d1d	2026-04-12 20:00:15.226655+00	2026-04-13 03:42:28.843419+00	t	\N	a1b2c3d4-e5f6-7890-abcd-ef1234567890	\N
egonzaga@conectamais.pro	$2b$12$oPp3Q70eQzrGAo/VBlFse.qh50i8.ntr02S46A6EtEFwjzkVMQGLG	Eliziel Gonzaga	\N	\N	admin	{module:dp,module:operacional,module:ged}	2026-07-07T14:24:51.849923	\N	81d35a73-90a3-4198-afa0-a2e1a2b01d07	2026-01-22 18:57:57.916305+00	2026-07-07 14:24:51.318524+00	t	\N	\N	\N
pedrorafaeldsn12@gmail.com	$2b$12$4hzTlUYB05iBrbNyh6ikcO5RPm6yrKWTzkoob0iiglhShI2Zj1qgi	Pedro rafael	\N	\N	pending	{module:dp,module:operacional,module:crm,module:ged,module:dev}	\N	\N	a77a52a9-82cf-4e1a-9df0-d5d292a4f724	2026-03-25 13:18:50.974497+00	2026-03-25 13:18:50.974497+00	t	109182265104822125815	\N	\N
mcp-service@conectamais.pro	$2b$12$b.8qpluAd.rjtojzGBMukezCW5OIFsF.f.72e2PLH4IlHn73SzxD2	Conecta MCP (servico CRM)	\N	\N	admin	{crm:read,crm:leads,crm:propostas,crm:oportunidades,crm:contatos,crm:clientes}	2026-07-09T19:01:16.674690	\N	01f4c6a0-743d-4702-8a1c-562ea57cfbe1	2026-06-23 22:35:36.859062+00	2026-07-09 19:01:16.418095+00	t	\N	\N	\N
ruansouza538@gmail.com	$2b$12$Ju87vk3FcB6zL8zBJ8N3OubXQObh2h/TqgcI3QJehHph7LY1Wcxzm	Ruan Souza	\N	\N	staff	{module:operacional,module:ged,module:crm}	2026-05-05T16:24:07.399726	\N	4b8efffd-d107-4097-a86a-8f2e0e79b85d	2026-05-05 14:04:19.793816+00	2026-05-05 21:37:04.439586+00	t	\N	\N	\N
josysouza2528@gmail.com	$2b$12$yi2DQQsmRNaG7aFHJcX82.i2orQ9zaLuhZjj9NG7chDGZWi0xWwbu	Josiane Test	\N	\N	funcionario	\N	2026-03-30T23:32:24.770724	\N	a48be421-96bc-4a53-b7b1-0cf651c79828	2026-03-30 23:16:36.005312+00	2026-03-30 23:32:24.510852+00	t	\N	\N	\N
admin@conectapro.com.br	$2b$12$A6i73pxrn8fzJiomsP2dxugZcrU21ChhUab.XZpNL7srf/k11XDGi	Administrador	\N	\N	admin	\N	2026-07-03T20:13:38.702099	\N	a1b2c3d4-e5f6-7890-abcd-ef1234567890	2026-01-13 03:54:11.725015+00	2026-07-03 20:13:38.333193+00	f	\N	\N	\N
\.


--
-- Name: users users_google_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_google_id_key UNIQUE (google_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: users users_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(id);


--
-- PostgreSQL database dump complete
--

\unrestrict XT1uYYELKRVubrQ6d4yVYWWqd3AFVx7on1NnLDOCNs1JGbl1GDEVHqiGKkAeIRx

