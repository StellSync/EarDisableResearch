"use client";
import { Grid, Typography, Button, Icon } from "@mui/material";
import { DataGrid } from "@mui/x-data-grid";
import { useRouter } from "next/navigation";
import VisibilityIcon from "@mui/icons-material/Visibility";

const rows = [
	{ id: 12345, lastName: "Sahan", firstName: "Nirmal", age: 14, gender: "Male" },
	{ id: 12232, lastName: "Bandara", firstName: "Silva", age: 31, gender: "Male" },
	{ id: 2345, lastName: "Lannister", firstName: "Jaime", age: 31, gender: "Male" },
	{ id: 112345, lastName: "Stark", firstName: "Arya", age: 11, gender: "Female" },
	{ id: 5, lastName: "Targaryen", firstName: "Daenerys", age: null, gender: "Female" },
	{ id: 6, lastName: "Melisandre", firstName: null, age: 150, gender: "Female" },
	{ id: 7, lastName: "Clifford", firstName: "Ferrara", age: 44, gender: "Male" },
	{ id: 8, lastName: "Frances", firstName: "Rossini", age: 36, gender: "Female" },
	{ id: 9, lastName: "Roxie", firstName: "Harvey", age: 65, gender: "Female" },
];

const DocView = () => {
	const router = useRouter();

	const columns = [
		{ field: "id", headerName: "ID", width: 90 },
		{
			field: "firstName",
			headerName: "First name",
			width: 200,
			editable: true,
		},
		{
			field: "lastName",
			headerName: "Last name",
			width: 200,
			editable: true,
		},
		{
			field: "age",
			headerName: "Age",
			type: "number",
			width: 150,
			editable: true,
        },
        {
			field: "gender",
			headerName: "Gender",
			width: 150,
			editable: true,
		},
		{
			field: "fullName",
			headerName: "Full name",
			description: "This column has a value getter and is not sortable.",
			sortable: false,
			width: 300,
			valueGetter: (value, row) =>
				`${row.firstName || ""} ${row.lastName || ""}`,
		},
		{
			field: "actions",
			headerName: "Actions",
			width: 120,
			sortable: false,
			renderCell: (params) => {
				const onClick = () => {
					router.push(`/patient/${params.row.id}`);
				};

				return (
					<Icon
						component={VisibilityIcon}
						onClick={onClick}
						sx={{ cursor: "pointer" }}
						color="primary"
					/>
				);
			},
		},
	];

	return (
		<Grid container sx={{ p: 2 }} direction="column" alignItems="center">
			<Grid item size={12} sx={{ mb: 4, textAlign: "center" }}>
				<Typography variant="h4" gutterBottom>
					Patients List
				</Typography>
			</Grid>
			<Grid item size={10} sx={{ mb: 4, textAlign: "center" }}>
				<DataGrid
					rows={rows}
					columns={columns}
					initialState={{
						pagination: {
							paginationModel: {
								pageSize: 7,
							},
						},
					}}
					pageSizeOptions={[5, 7, 10, 20, 50]}
					disableRowSelectionOnClick
				/>
			</Grid>
		</Grid>
	);
};

export default DocView;
