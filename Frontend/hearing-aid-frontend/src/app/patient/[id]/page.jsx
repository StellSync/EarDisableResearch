"use client";
import { useParams } from "next/navigation";
import {
	Grid,
	Typography,
	Paper,
	Button,
	Card,
	CardContent,
	Box,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import PatientApis from "@/apis/PatientApis";
import { LineChart } from "@mui/x-charts/LineChart";
import CircularProgress from "@mui/material/CircularProgress";

const PatientView = () => {
	const router = useRouter();
	const params = useParams();
	const patientId = params.id;

	const [filteredData, setFilteredData] = useState([]);
	const [characterStats, setCharacterStats] = useState({});
	const [isLoading, setIsLoading] = useState(true);

	const [timeSeriesData, setTimeSeriesData] = useState({
		swara: [],
		wiyanjana: [],
		sentence: [],
	});

	// Process the patient data
	const processPatientData = (data) => {
		const characterStats = {};
		const activityData = {
			swara: [],
			wiyanjana: [],
			sentence: [],
		};

		// Initialize stats for all tested characters
		data.forEach((item) => {
			if (
				item.chosen_option === "similar" ||
				item.chosen_option === "correct"
			) {
				let char;
				// Handle different activities
				if (item.activity === "swara") {
					char = item.vowel;
				} else if (item.activity === "sentence") {
					char = item.vowel; // Group all sentences together
				} else if (item.activity === "wiyanjana") {
					char = item.consonant_tested.character;
				}

				if (!characterStats[char]) {
					characterStats[char] = {
						similar: 0,
						correct: 0,
						total: 0,
						activity: item.activity,
					};
				}
			}
		});

		// Count responses and track accuracy over time
		const similarData = [];
		data.forEach((item) => {
			let char;
			if (item.activity === "swara") {
				char = item.vowel;
			} else if (item.activity === "sentence") {
				char = item.vowel;
			} else if (item.activity === "wiyanjana") {
				char = item.consonant_tested.character;
			}

			if (characterStats[char]) {
				if (item.chosen_option === "similar") {
					characterStats[char].similar++;
					similarData.push(item);
				} else if (item.chosen_option === "correct") {
					characterStats[char].correct++;
				}
				characterStats[char].total++;

				// Track accuracy by attempt number for each activity
				const accuracy =
					(characterStats[char].correct / characterStats[char].total) * 100;

				// If this activity doesn't have any attempts yet, initialize attempt counter
				if (!activityData[item.activity].length) {
					activityData[item.activity].push({
						attempt: 1,
						accuracy,
						character: char,
					});
				} else {
					// Add next attempt number
					activityData[item.activity].push({
						attempt: activityData[item.activity].length + 1,
						accuracy,
						character: char,
					});
				}
			}
		});

		// Sort time series data by timestamp
		Object.keys(activityData).forEach((activity) => {
			activityData[activity].sort((a, b) => a.timestamp - b.timestamp);
		});

		return {
			filteredData: similarData,
			characterStats,
			timeSeriesData: activityData,
		};
	};

	useEffect(() => {
		// Fetch patient data from the API
		const fetchPatientData = async () => {
			try {
				setIsLoading(true);
				const data = await PatientApis.getPatientResults(patientId);
				// Process the fetched data
				const { filtered, characterStats, timeSeriesData } = processPatientData(
					data?.data?.items
				);
				setFilteredData(filtered);
				setCharacterStats(characterStats);
				setTimeSeriesData(timeSeriesData);
				setIsLoading(false);
			} catch (error) {
				console.error("Error fetching patient data:", error);
			}
		};
		fetchPatientData();
	}, [patientId]);

	return (
		<Grid container spacing={3} sx={{ p: 3 }}>
			<Grid item size={12}>
				<Button
					startIcon={<ArrowBackIcon />}
					onClick={() => router.back()}
					sx={{ mb: 2 }}
				>
					Back to Patients
				</Button>
				<Typography variant="h4" gutterBottom>
					Patient Details
				</Typography>
			</Grid>

			<Grid item size={12}>
				{isLoading ? (
					<Grid container justifyContent="center" alignItems="center">
						<Grid item size={12} sx={{ textAlign: "center", mt: 30 }}>
							<CircularProgress />
						</Grid>
						<Grid item size={12} sx={{ textAlign: "center", mt: 2 }}>
							<Typography variant="body1">Loading Data...</Typography>
						</Grid>
					</Grid>
				) : (
					<>
						<Grid item size={12}>
							<Paper sx={{ p: 3 }}>
								<Typography variant="h6" gutterBottom>
									Accuracy Over Time
								</Typography>
								<LineChart
									xAxis={[
										{
											data: Array.from(
												{
													length: Math.max(
														timeSeriesData.swara.length,
														timeSeriesData.wiyanjana.length,
														timeSeriesData.sentence.length
													),
												},
												(_, i) => i + 1
											),
											label: "Attempts",
											scaleType: "linear",
										},
									]}
									yAxis={[
										{
											label: "Accuracy (%)",
										},
									]}
									series={[
										{
											data: timeSeriesData.swara.map((item) => item.accuracy),
											label: "Vowels",
											color: "#2196f3",
											showMark: true,
										},
										{
											data: timeSeriesData.wiyanjana.map(
												(item) => item.accuracy
											),
											label: "Consonants",
											color: "#4caf50",
											showMark: true,
										},
										{
											data: timeSeriesData.sentence.map(
												(item) => item.accuracy
											),
											label: "Sentences",
											color: "#ff9800",
											showMark: true,
										},
									]}
									height={400}
									sx={{
										".MuiLineElement-root": {
											strokeWidth: 2,
										},
									}}
								/>
							</Paper>
						</Grid>
						<Grid item size={12}>
							<Grid container spacing={3} sx={{ p: 3 }} justifyContent="center">
								<Grid item size={10} sx={{ alignContent: "center" }}>
									<Paper sx={{ p: 3 }}>
										<Typography variant="h6" gutterBottom>
											Correct Response Analysis
										</Typography>
										<Grid container spacing={2}>
											{Object.entries(characterStats)
												.filter(([_, stats]) => stats.correct === stats.total)
												.map(([char, stats]) => (
													<Grid item xs={12} sm={6} md={4} lg={3} key={char}>
														<Card>
															<CardContent>
																<Typography
																	variant="h5"
																	gutterBottom
																	color={"success.main"}
																>
																	{char}
																</Typography>
																<Typography color="textSecondary" gutterBottom>
																	Correct: {stats.correct}
																</Typography>
																<Typography color="textSecondary">
																	Total Tests: {stats.total}
																</Typography>
															</CardContent>
														</Card>
													</Grid>
												))}
										</Grid>
									</Paper>
								</Grid>

								{/* Response Analysis */}
								<Grid item size={10} sx={{ justifyContent: "center" }}>
									<Paper sx={{ p: 3 }}>
										<Typography variant="h6" gutterBottom>
											Incorrect Response Analysis
										</Typography>
										<Grid container spacing={2}>
											{Object.entries(characterStats)
												.filter(([_, stats]) => stats.similar >= 1)
												.map(([char, stats]) => (
													<Grid item xs={12} sm={6} md={4} lg={3} key={char}>
														<Card>
															<CardContent>
																<Typography
																	variant="h5"
																	gutterBottom
																	color={
																		stats.similar === stats.total
																			? "error.main"
																			: "info"
																	}
																>
																	{char}
																</Typography>
																<Typography color="textSecondary" gutterBottom>
																	Incorrect: {stats.similar}
																</Typography>
																<Typography color="textSecondary">
																	Total Tests: {stats.total}
																</Typography>
															</CardContent>
														</Card>
													</Grid>
												))}
										</Grid>
									</Paper>
								</Grid>
							</Grid>
						</Grid>
					</>
				)}
			</Grid>
		</Grid>
	);
};

export default PatientView;
