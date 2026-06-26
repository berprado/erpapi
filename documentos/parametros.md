#master_table

id	nombre	descripcion	estado
1	cargos	Cargos en la empresa	HAB
2	grupo_productos	Grupo de productos	HAB
3	unidad_medida_display	Unidad de medida display	HAB
4	unidad_medida_detalle	Unidad de medida Detalle	HAB
5	estados_solicitud	Estados de solicitud Barra	HAB
6	estado_operacion	Estados de operación	HAB
7	estado_comanda	Estados de comanda	HAB
8	parametros_generales	Parametros Generales	HAB
9	estado_conciliacion	Estado de Conciliación	HAB
10	estado_impresion_com	Estado Impresión Comanda	HAB
11	tipo_salida_almacen	Tipo de Salida de Almacen	HAB
12	tipo_parte_combo	Tipo parte combo	HAB
13	tipo_documento_ingreso	Tipo de documento de ingreso	HAB
14	estado_solicitud_producto	Estado de solicitud de productos	HAB
15	tipo_salida_comanda	tipo de salida de comanda	HAB
16	estado_detalle_orden_compra	Estado detalle orden compra	HAB
17	estado_registro_inventario_fisico	Estado de registro inventario Fisico	HAB
18	key	key	HAB
19	tipo_movimiento_dinero	Tipo de movimiento dinero	HAB
20	permite_comandas	permite comandas	HAB
21	tipo_movimiento_valoracion	Tipo de movimiento Valoracion	HAB
22	tipo_salida_inventario	Tipo de salida de inventario	HAB
23	tipo_ingreso	Tipo de Ingreso	HAB
24	tipo_salida	Tipo de Salida	HAB

#parameter_table

id	nombre	descripcion	texto1	texto2	fechaInicio	fechaFin	numero1	numero2	id_master	orden	requerido	estado
1	ADMINISTRACION	SISTEMA			(null)	(null)	0	0,00	1	1	0	HAB
2	Gerencia Financiera	Gerencia financiera			(null)	(null)	0	0,00	1	2	0	HAB
3	Administrador	administracion general			(null)	(null)	0	0,00	1	3	0	HAB
4	Barman	Barman			(null)	(null)	0	0,00	1	4	0	HAB
5	Mesera(o)	Mesero			(null)	(null)	0	0,00	1	5	0	HAB
6	Jefe de Sistemas	Jefe de sistemas			(null)	(null)	0	0,00	1	6	0	HAB
7	Almacenes	Almacenes			(null)	(null)	0	0,00	1	7	0	HAB
8	BEBIDA	Bebida			(null)	(null)	0	0,00	2	1	0	HAB
9	BOCADITO	Bocadito			(null)	(null)	0	0,00	2	2	0	HAB
10	SOUVENIR	Souvenir			(null)	(null)	0	0,00	2	3	0	HAB
11	ML	Mililitro(s) Display			(null)	(null)	0	0,00	3	1	0	HAB
12	UNID	Unidad(es) Display			(null)	(null)	0	0,00	3	2	0	HAB
13	KG	Kilogramo(s) Display			(null)	(null)	0	0,00	3	3	0	HAB
14	Oz.	Onza(s)			(null)	(null)	0	0,00	4	1	0	HAB
15	Gr.	Gramo(s)			(null)	(null)	0	0,00	4	2	0	HAB
16	PENDIETE				(null)	(null)	0	0,00	5	1	0	HAB
17	SOLICITADO				(null)	(null)	0	0,00	5	2	0	HAB
18	ATENDIDO				(null)	(null)	0	0,00	5	3	0	HAB
19	ANULADO				(null)	(null)	0	0,00	5	4	0	HAB
20	PROCESADO				(null)	(null)	0	0,00	5	5	0	HAB
21	EN BARRA				(null)	(null)	0	0,00	5	6	0	HAB
22	EN PROCESO				(null)	(null)	0	0,00	6	1	0	HAB
23	CERRADO				(null)	(null)	0	0,00	6	2	0	HAB
24	INICIO CIERRE				(null)	(null)	0	0,00	6	3	0	HAB
25	PENDIENTE		PEND		(null)	(null)	0	0,00	7	1	0	HAB
26	PROCESADO		PROC		(null)	(null)	0	0,00	7	2	0	HAB
27	ANULADO		ANUL		(null)	(null)	0	0,00	7	3	0	HAB
28	EXITOSO				(null)	(null)	0	0,00	9	1	0	HAB
29	OBSERVADO				(null)	(null)	0	0,00	9	2	0	HAB
30	comision_generica	Comision para las meseras			(null)	(null)	5	0,00	8	1	0	HAB
31	IMPRESO	Impresión correcta de la comanda			(null)	(null)	0	0,00	10	1	0	HAB
32	PENDIENTE	Pendiente de imprimir			(null)	(null)	0	0,00	10	2	0	HAB
33	PROVEEDOR	Salida a proveedor			(null)	(null)	0	0,00	11	1	0	HAB
34	BARRA	Salida a barra			(null)	(null)	0	0,00	11	2	0	HAB
35	RECHAZADO	Rechazado por barra			(null)	(null)	0	0,00	5	7	0	HAB
36	PRINCIPAL	Producto principal			(null)	(null)	0	0,00	12	1	0	HAB
37	OPCIONAL	Producto opciones			(null)	(null)	0	0,00	12	2	0	HAB
38	FACTURA	Factura			(null)	(null)	0	0,00	13	1	0	HAB
39	RECIBO	Recibo			(null)	(null)	0	0,00	13	2	0	HAB
40	OTRO	Otro			(null)	(null)	0	0,00	13	3	0	HAB
41	PENDIENTE	Pendiente			(null)	(null)	0	0,00	14	1	0	HAB
42	CONFIRMADO	Confirmado			(null)	(null)	0	0,00	14	2	0	HAB
43	ANULADO	Anulado			(null)	(null)	0	0,00	14	3	0	HAB
44	REFRESCOS	Refrescos			(null)	(null)	0	0,00	2	4	0	HAB
45	CIGARRILLOS	Cigarrillos			(null)	(null)	0	0,00	2	5	0	HAB
46	OTROS	Otros			(null)	(null)	0	0,00	2	6	0	HAB
47	Cu.	Cuchara(s)			(null)	(null)	0	0,00	4	3		HAB
48	Taj.	Tajada(s)			(null)	(null)	0	0,00	4	4		HAB
49	Porc.	Porcion(es)			(null)	(null)	0	0,00	4	5		HAB
50	VENTA	VENTA			(null)	(null)	0	0,00	15	1	0	HAB
51	CORTESIA	CORTESIA			(null)	(null)	0	0,00	15	2	0	HAB
54	AREAS	Salida a area			(null)	(null)	0	0,00	11	3	0	HAB
55	CONFIRMADO	Estado confirmado			(null)	(null)	0	0,00	16	1	0	HAB
56	PENDIENTE	Estado Pendiendte			(null)	(null)	0	0,00	16	2	0	HAB
57	Unid.	Unidad(es)			(null)	(null)	0	0,00	4	6	0	HAB
58	EQUIPOS ELECTRONICOS	EQUIPOS ELECTRONICOS			(null)	(null)	0	0,00	2	5	0	HAB
59	MUEBLES Y ENSERES	MUEBLES Y ENSERES			(null)	(null)	0	0,00	2	5	0	HAB
60	ESTRUCTURAS 	ESTRUCTURAS 			(null)	(null)	0	0,00	2	5	0	HAB
61	GR	Gramo(s) Display			(null)	(null)	0	0,00	3	4	0	HAB
62	EN PROCESO	EN PROCESO			(null)	(null)	0	0,00	17	1	0	HAB
63	FINALIZADO	FINALIZADO			(null)	(null)	0	0,00	17	2	0	HAB
64	MATERIAL DE ESCRITORIO	mat escritorio			(null)	(null)	0	0,00	2	5	0	HAB
65	ENCERES Y UTENCILLOS DE BARRA	articulos varios de barra			(null)	(null)	0	0,00	2	6	0	HAB
66	Compra Definitiva	Compra Definitiva			(null)	(null)	0	0,00	18	1	0	HAB
67	Alquiler	Alquiler			(null)	(null)	0	0,00	18	1	0	HAB
68	Ingreso	Ingreso			(null)	(null)	0	0,00	19	1	0	HAB
69	Egreso	Egreso			(null)	(null)	0	0,00	19	2	0	HAB
70	Si	Permite comandar			(null)	(null)	0	0,00	20	1	0	HAB
71	No	No permite comandar			(null)	(null)	0	0,00	20	2	0	HAB
72	Correlativo Producto	Correlativo Producto			(null)	(null)	10038	0,00	8	2	0	HAB
74	INGRESO	INGRESO			(null)	(null)	0	0,00	21	1	0	HAB
75	SALIDA	EGRESO			(null)	(null)	0	0,00	21	2	0	HAB
76	MOVIMIENTO	MOVIMIENTO			(null)	(null)	0	0,00	22	1	0	HAB
77	BAJA POR AJUSTE	BAJA POR AJUSTE			(null)	(null)	0	0,00	22	2	0	HAB
78	BAJA POR AJUSTE				(null)	(null)	0	0,00	21	3	0	HAB
79	INICIAL	INICIAL			(null)	(null)	0	0,00	21	4	0	HAB
80	PROVEEDOR	PROVEEDOR			(null)	(null)	0	0,00	23	1	0	HAB
81	INGRESO POR AJUSTE	INGRESO POR AJUSTE			(null)	(null)	0	0,00	23	2	0	HAB
82	AJUSTE	AJUSTE			(null)	(null)	0	0,00	13	4	0	HAB
83	SALIDA PRODUCTO	SALIDA PRODUCTO			(null)	(null)	0	0,00	24	1	0	HAB
84	AJUSTE	AJUSTE			(null)	(null)	0	0,00	24	2	0	HAB
85	Jarra.	Jarra(s)			(null)	(null)	0	0,00	4	7	0	HAB
86	Copa.	Copa(s)			(null)	(null)	0	0,00	4	8	0	HAB
87	BOTxPer	Botella Personal			(null)	(null)	0	0,00	3	5	0	HAB
88	LATA	Lata(s) Display			(null)	(null)	0	0,00	3	6	0	HAB
89	PAQ	Paquete Display			(null)	(null)	0	0,00	3	7	0	HAB
90	BOTx3L	Botella 3LT			(null)	(null)	0	0,00	3	8	0	HAB
91	Vaso.	Vaso(s)			(null)	(null)	0	0,00	4	9	0	HAB
92	Shot.	Shot(s)			(null)	(null)	0	0,00	4	10	0	HAB
93	Taza.	Taza(s)			(null)	(null)	0	0,00	4	11	0	HAB
94	Bx2LT	Botella 2LT			(null)	(null)	0	0,00	3	9	0	HAB
95	BOTx1.5L	Botella 1.5LT			(null)	(null)	0	0,00	3	10	0	HAB
96	BOTx1LT	Botella 1LT			(null)	(null)	0	0,00	3	11	0	HAB