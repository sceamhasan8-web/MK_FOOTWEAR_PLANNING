package com.footwear.erp.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import com.footwear.erp.api.ErpApiClient
import com.footwear.erp.models.*

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(
                colorScheme = darkColorScheme(
                    primary = Color(0xFF2563EB),
                    secondary = Color(0xFF10B981),
                    background = Color(0xFF0F172A),
                    surface = Color(0xFF1E293B),
                )
            ) {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    AndroidAppRoot()
                }
            }
        }
    }
}

enum class AndroidTab {
    ENTRY,
    LOOKUP,
    DASHBOARD
}

@Composable
fun AndroidAppRoot() {
    // Configurable central server IP/port for local Wi-Fi factory network
    var serverHost by remember { mutableStateOf("10.0.2.2:8000") } // Android emulator host localhost
    val apiClient = remember(serverHost) { ErpApiClient(baseUrl = "http://$serverHost/api/v1") }
    val scope = rememberCoroutineScope()

    var isLoggedIn by remember { mutableStateOf(false) }
    var currentTab by remember { mutableStateOf(AndroidTab.ENTRY) }

    var username by remember { mutableStateOf("supervisor") }
    var password by remember { mutableStateOf("supervisor123") }
    var loginError by remember { mutableStateOf<String?>(null) }

    if (!isLoggedIn) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text("Footwear ERP Mobile", fontSize = 24.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
            Text("Shop-Floor Daily Production Terminal", fontSize = 13.sp, color = Color.Gray, modifier = Modifier.padding(bottom = 24.dp))

            OutlinedTextField(
                value = serverHost,
                onValueChange = { serverHost = it },
                label = { Text("Server Host (IP:Port)") },
                modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp)
            )
            OutlinedTextField(
                value = username,
                onValueChange = { username = it },
                label = { Text("Username") },
                modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp)
            )
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("Password") },
                modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp)
            )

            loginError?.let {
                Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp, modifier = Modifier.padding(bottom = 8.dp))
            }

            Button(
                onClick = {
                    scope.launch {
                        val res = apiClient.login(username, password)
                        if (res.isSuccess) {
                            isLoggedIn = true
                        } else {
                            loginError = res.exceptionOrNull()?.message ?: "Login failed"
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth().height(50.dp)
            ) {
                Text("Sign In as Supervisor")
            }
        }
    } else {
        Scaffold(
            bottomBar = {
                NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                    NavigationBarItem(
                        selected = currentTab == AndroidTab.ENTRY,
                        onClick = { currentTab = AndroidTab.ENTRY },
                        label = { Text("Entry") },
                        icon = {}
                    )
                    NavigationBarItem(
                        selected = currentTab == AndroidTab.LOOKUP,
                        onClick = { currentTab = AndroidTab.LOOKUP },
                        label = { Text("Orders") },
                        icon = {}
                    )
                    NavigationBarItem(
                        selected = currentTab == AndroidTab.DASHBOARD,
                        onClick = { currentTab = AndroidTab.DASHBOARD },
                        label = { Text("Status") },
                        icon = {}
                    )
                }
            }
        ) { padding ->
            Box(modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp)) {
                when (currentTab) {
                    AndroidTab.ENTRY -> AndroidProductionEntryScreen(apiClient)
                    AndroidTab.LOOKUP -> AndroidOrderLookupScreen(apiClient)
                    AndroidTab.DASHBOARD -> AndroidDashboardScreen(apiClient)
                }
            }
        }
    }
}

@Composable
fun AndroidProductionEntryScreen(apiClient: ErpApiClient) {
    var orders by remember { mutableStateOf<List<OrderSummaryDto>>(emptyList()) }
    var selectedOrder by remember { mutableStateOf<OrderDetailDto?>(null) }
    var selectedRouteId by remember { mutableStateOf<Int?>(null) }
    var selectedOpId by remember { mutableStateOf<Int?>(null) }
    var quantity by remember { mutableStateOf("") }
    var acceptedQty by remember { mutableStateOf("") }
    var rejectedQty by remember { mutableStateOf("0") }
    var remarks by remember { mutableStateOf("") }
    var message by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        orders = apiClient.getOrders().getOrDefault(emptyList())
    }

    Column(modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Daily Production Entry", fontSize = 20.sp, fontWeight = FontWeight.Bold)

        // Select Order
        Text("Select Order:", fontSize = 12.sp, color = Color.Gray)
        LazyColumn(modifier = Modifier.height(100.dp)) {
            items(orders) { o ->
                Surface(
                    modifier = Modifier.fillMaxWidth().clickable {
                        scope.launch {
                            val det = apiClient.getOrderDetail(o.id).getOrNull()
                            selectedOrder = det
                            selectedRouteId = det?.routes?.firstOrNull()?.id
                            selectedOpId = det?.routes?.firstOrNull()?.operations?.firstOrNull()?.id
                        }
                    },
                    color = if (selectedOrder?.id == o.id) MaterialTheme.colorScheme.primary.copy(alpha = 0.2f) else Color.Transparent,
                    shape = RoundedCornerShape(6.dp)
                ) {
                    Text("${o.order_code} - ${o.style_model}", modifier = Modifier.padding(8.dp), fontSize = 13.sp)
                }
            }
        }

        selectedOrder?.let { det ->
            Text("Operation to Record:", fontSize = 12.sp, color = Color.Gray)
            det.routes.forEach { r ->
                r.operations.forEach { op ->
                    Surface(
                        modifier = Modifier.fillMaxWidth().clickable {
                            selectedRouteId = r.id
                            selectedOpId = op.id
                        },
                        color = if (selectedOpId == op.id) MaterialTheme.colorScheme.secondary.copy(alpha = 0.2f) else Color.Transparent,
                        shape = RoundedCornerShape(6.dp)
                    ) {
                        Row(modifier = Modifier.padding(8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("${r.section_name} -> ${op.operation_name}", fontSize = 13.sp)
                            Text("Bal: %,.0f".format(op.balance_quantity), fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
                        }
                    }
                }
            }

            OutlinedTextField(
                value = quantity,
                onValueChange = {
                    quantity = it
                    acceptedQty = it
                },
                label = { Text("Accepted Output Quantity") },
                modifier = Modifier.fillMaxWidth()
            )

            // Quick add buttons
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(500, 1000, 2000, 5000).forEach { amt ->
                    Button(
                        onClick = {
                            val cur = quantity.toDoubleOrNull() ?: 0.0
                            val nextVal = (cur + amt).toInt().toString()
                            quantity = nextVal
                            acceptedQty = nextVal
                        },
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("+$amt", fontSize = 11.sp)
                    }
                }
            }

            OutlinedTextField(
                value = rejectedQty,
                onValueChange = { rejectedQty = it },
                label = { Text("Rejected Qty (Wastage)") },
                modifier = Modifier.fillMaxWidth()
            )

            OutlinedTextField(
                value = remarks,
                onValueChange = { remarks = it },
                label = { Text("Remarks (Shift / Line)") },
                modifier = Modifier.fillMaxWidth()
            )

            Button(
                onClick = {
                    scope.launch {
                        val res = apiClient.recordProductionEntry(
                            orderId = det.id,
                            routeId = selectedRouteId ?: det.routes.first().id,
                            operationId = selectedOpId ?: det.routes.first().operations.first().id,
                            entryDate = "2026-10-07",
                            quantity = quantity.toDoubleOrNull() ?: 0.0,
                            acceptedQty = acceptedQty.toDoubleOrNull() ?: 0.0,
                            rejectedQty = rejectedQty.toDoubleOrNull() ?: 0.0,
                            remarks = remarks
                        )
                        if (res.isSuccess) {
                            message = "Entry recorded successfully!"
                            quantity = ""
                            acceptedQty = ""
                            selectedOrder = apiClient.getOrderDetail(det.id).getOrNull()
                        } else {
                            message = "Error: " + (res.exceptionOrNull()?.message ?: "Failed")
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth().height(48.dp)
            ) {
                Text("Confirm Shop-Floor Entry")
            }

            message?.let {
                Text(it, color = if (it.startsWith("Error")) MaterialTheme.colorScheme.error else Color(0xFF10B981))
            }
        }
    }
}

@Composable
fun AndroidOrderLookupScreen(apiClient: ErpApiClient) {
    var orders by remember { mutableStateOf<List<OrderSummaryDto>>(emptyList()) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        orders = apiClient.getOrders().getOrDefault(emptyList())
    }

    Column(modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Order Production Lookup", fontSize = 20.sp, fontWeight = FontWeight.Bold)
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(orders) { o ->
                Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(o.order_code, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                            Text(o.status, color = MaterialTheme.colorScheme.primary, fontSize = 12.sp)
                        }
                        Text("${o.buyer_name} - ${o.style_model}", fontSize = 13.sp)
                        Text("Ordered: %,.0f | Done: %,.0f (${o.completion_percentage}%)".format(o.total_quantity, o.completed_pairs), fontSize = 12.sp, color = Color.Gray)
                        Text("Delivery: ${o.current_delivery_date} (${o.remaining_working_days} workdays left)", fontSize = 12.sp, color = Color(0xFFF59E0B))
                    }
                }
            }
        }
    }
}

@Composable
fun AndroidDashboardScreen(apiClient: ErpApiClient) {
    var summary by remember { mutableStateOf<DashboardSummaryDto?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        summary = apiClient.getDashboardSummary().getOrNull()
    }

    Column(modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Plant Status Overview", fontSize = 20.sp, fontWeight = FontWeight.Bold)

        summary?.let { s ->
            Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Today's Output Status", fontWeight = FontWeight.Bold)
                    Text("Planned Today: %,.0f pairs".format(s.today_total_planned))
                    Text("Actual Today: %,.0f pairs".format(s.today_total_actual))
                    val variance = s.today_total_actual - s.today_total_planned
                    Text("Variance: %+.0f pairs".format(variance), color = if (variance >= 0) Color(0xFF10B981) else Color(0xFFEF4444), fontWeight = FontWeight.Bold)
                }
            }

            Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Order Health", fontWeight = FontWeight.Bold)
                    Text("Due Today: ${s.orders_due_today}")
                    Text("Overdue Orders: ${s.overdue_orders_count}", color = Color(0xFFEF4444))
                    Text("Sections Lagging: ${s.sections_behind_count}", color = Color(0xFFEF4444))
                }
            }
        } ?: CircularProgressIndicator()
    }
}
