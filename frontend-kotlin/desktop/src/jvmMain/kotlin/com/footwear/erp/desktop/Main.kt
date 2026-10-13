package com.footwear.erp.desktop

import androidx.compose.desktop.ui.tooling.preview.Preview
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
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import kotlinx.coroutines.launch
import com.footwear.erp.api.ErpApiClient
import com.footwear.erp.models.*
import java.awt.Desktop
import java.net.URI

enum class Screen {
    DASHBOARD,
    BUYERS,
    ORDERS,
    PRODUCTION_ENTRY,
    REPORTS
}

fun main() = application {
    val windowState = rememberWindowState(width = 1360.dp, height = 860.dp)
    Window(
        onCloseRequest = ::exitApplication,
        state = windowState,
        title = "Footwear Manufacturing Production Planning ERP - Desktop Office Edition"
    ) {
        MaterialTheme(
            colorScheme = darkColorScheme(
                primary = Color(0xFF2563EB),
                secondary = Color(0xFF0D9488),
                background = Color(0xFF0F172A),
                surface = Color(0xFF1E293B),
                onPrimary = Color.White,
                onSurface = Color(0xFFF8FAFC)
            )
        ) {
            Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                AppRoot()
            }
        }
    }
}

@Composable
fun AppRoot() {
    val apiClient = remember { ErpApiClient() }
    val scope = rememberCoroutineScope()
    var isLoggedIn by remember { mutableStateOf(false) }
    var currentScreen by remember { mutableStateOf(Screen.DASHBOARD) }

    var username by remember { mutableStateOf("admin") }
    var password by remember { mutableStateOf("admin123") }
    var loginError by remember { mutableStateOf<String?>(null) }
    var isLoading by remember { mutableStateOf(false) }

    if (!isLoggedIn) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Card(
                modifier = Modifier.width(420.dp).padding(24.dp),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
            ) {
                Column(
                    modifier = Modifier.padding(28.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    Text(
                        "Footwear ERP Login",
                        fontSize = 22.sp,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    Text(
                        "Centralized Production Planning & Tracking",
                        fontSize = 13.sp,
                        color = Color.Gray
                    )

                    OutlinedTextField(
                        value = username,
                        onValueChange = { username = it },
                        label = { Text("Username") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        label = { Text("Password") },
                        modifier = Modifier.fillMaxWidth()
                    )

                    loginError?.let {
                        Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp)
                    }

                    Button(
                        onClick = {
                            isLoading = true
                            loginError = null
                            scope.launch {
                                val result = apiClient.login(username, password)
                                isLoading = false
                                if (result.isSuccess) {
                                    isLoggedIn = true
                                } else {
                                    loginError = result.exceptionOrNull()?.message ?: "Login failed"
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth().height(48.dp),
                        enabled = !isLoading
                    ) {
                        Text(if (isLoading) "Authenticating..." else "Sign In")
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        TextButton(onClick = { username = "admin"; password = "admin123" }) {
                            Text("Demo Admin", fontSize = 11.sp)
                        }
                        TextButton(onClick = { username = "planner"; password = "planner123" }) {
                            Text("Demo Planner", fontSize = 11.sp)
                        }
                        TextButton(onClick = { username = "supervisor"; password = "supervisor123" }) {
                            Text("Demo Supervisor", fontSize = 11.sp)
                        }
                    }
                }
            }
        }
    } else {
        Row(modifier = Modifier.fillMaxSize()) {
            // Sidebar Navigation
            Sidebar(
                currentScreen = currentScreen,
                onScreenSelect = { currentScreen = it },
                onLogout = {
                    apiClient.authToken = null
                    isLoggedIn = false
                },
                userFullName = apiClient.currentUser?.full_name ?: "User",
                userRole = apiClient.currentUser?.role ?: "Viewer"
            )

            // Main Content Area
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .padding(24.dp)
            ) {
                when (currentScreen) {
                    Screen.DASHBOARD -> DashboardScreen(apiClient)
                    Screen.BUYERS -> BuyersScreen(apiClient)
                    Screen.ORDERS -> OrdersScreen(apiClient)
                    Screen.PRODUCTION_ENTRY -> ProductionEntryScreen(apiClient)
                    Screen.REPORTS -> ReportsScreen(apiClient)
                }
            }
        }
    }
}

@Composable
fun Sidebar(
    currentScreen: Screen,
    onScreenSelect: (Screen) -> Unit,
    onLogout: () -> Unit,
    userFullName: String,
    userRole: String
) {
    Card(
        modifier = Modifier.width(260.dp).fillMaxHeight(),
        shape = RoundedCornerShape(0.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(16.dp),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    "FOOTWEAR ERP",
                    fontWeight = FontWeight.Black,
                    fontSize = 18.sp,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(bottom = 16.dp, top = 8.dp)
                )

                SidebarItem("Executive Dashboard", currentScreen == Screen.DASHBOARD) { onScreenSelect(Screen.DASHBOARD) }
                SidebarItem("Buyer Management", currentScreen == Screen.BUYERS) { onScreenSelect(Screen.BUYERS) }
                SidebarItem("Order Planning", currentScreen == Screen.ORDERS) { onScreenSelect(Screen.ORDERS) }
                SidebarItem("Daily Production Entry", currentScreen == Screen.PRODUCTION_ENTRY) { onScreenSelect(Screen.PRODUCTION_ENTRY) }
                SidebarItem("Reports & Exports", currentScreen == Screen.REPORTS) { onScreenSelect(Screen.REPORTS) }
            }

            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Divider(color = Color.DarkGray)
                Text(userFullName, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                Text("Role: ${userRole.uppercase()}", fontSize = 11.sp, color = Color.Gray)
                OutlinedButton(
                    onClick = onLogout,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Logout")
                }
            }
        }
    }
}

@Composable
fun SidebarItem(title: String, isSelected: Boolean, onClick: () -> Unit) {
    val bg = if (isSelected) MaterialTheme.colorScheme.primary.copy(alpha = 0.2f) else Color.Transparent
    val textColor = if (isSelected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface
    Surface(
        modifier = Modifier.fillMaxWidth().clickable { onClick() },
        color = bg,
        shape = RoundedCornerShape(8.dp)
    ) {
        Text(
            title,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
            fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
            color = textColor,
            fontSize = 14.sp
        )
    }
}

@Composable
fun DashboardScreen(apiClient: ErpApiClient) {
    var summary by remember { mutableStateOf<DashboardSummaryDto?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        scope.launch {
            summary = apiClient.getDashboardSummary().getOrNull()
        }
    }

    Column(modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(20.dp)) {
        Text("Executive Production Dashboard", fontSize = 24.sp, fontWeight = FontWeight.Bold)

        summary?.let { s ->
            // Metric Cards
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                MetricCard("Active Orders", "${s.active_orders_count}", "Orders in production", Modifier.weight(1f))
                MetricCard("Total Ordered Pairs", "%,.0f".format(s.total_ordered_pairs), "Active commitments", Modifier.weight(1f))
                MetricCard("Completed Pairs", "%,.0f".format(s.completed_pairs), "Finished production", Modifier.weight(1f))
                MetricCard("Outstanding Balance", "%,.0f".format(s.outstanding_production_pairs), "Pairs to deliver", Modifier.weight(1f))
            }

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                MetricCard("Orders Due Today", "${s.orders_due_today}", "Critical dispatch", Modifier.weight(1f), Color(0xFFF59E0B))
                MetricCard("Due in 7 Days", "${s.orders_due_7_days}", "Upcoming deadlines", Modifier.weight(1f))
                MetricCard("Overdue Orders", "${s.overdue_orders_count}", "Past deadline", Modifier.weight(1f), Color(0xFFEF4444))
                MetricCard("Sections Behind Plan", "${s.sections_behind_count}", "Lagging output", Modifier.weight(1f), Color(0xFFEF4444))
            }

            Text("Department Daily Target Performance", fontSize = 18.sp, fontWeight = FontWeight.Bold)
            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(s.section_performances) { p ->
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp).fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column {
                                Text(p.section_name, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                                Text("Category: ${p.category_name}", fontSize = 12.sp, color = Color.Gray)
                            }
                            Text("Planned Today: %,.0f".format(p.total_planned_today))
                            Text("Actual Today: %,.0f".format(p.total_actual_today))
                            val varColor = if (p.variance >= 0) Color(0xFF10B981) else Color(0xFFEF4444)
                            Text("Variance: %+.0f".format(p.variance), color = varColor, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        } ?: CircularProgressIndicator()
    }
}

@Composable
fun MetricCard(title: String, value: String, subtitle: String, modifier: Modifier = Modifier, accent: Color? = null) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(title, fontSize = 12.sp, color = Color.Gray)
            Text(value, fontSize = 24.sp, fontWeight = FontWeight.Bold, color = accent ?: MaterialTheme.colorScheme.onSurface)
            Text(subtitle, fontSize = 11.sp, color = Color.DarkGray)
        }
    }
}

@Composable
fun BuyersScreen(apiClient: ErpApiClient) {
    var buyers by remember { mutableStateOf<List<BuyerSummary>>(emptyList()) }
    var search by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    fun loadBuyers() {
        scope.launch {
            buyers = apiClient.getBuyers(if (search.isBlank()) null else search).getOrDefault(emptyList())
        }
    }

    LaunchedEffect(Unit) { loadBuyers() }

    Column(modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("Buyer Management", fontSize = 24.sp, fontWeight = FontWeight.Bold)
            OutlinedTextField(
                value = search,
                onValueChange = { search = it; loadBuyers() },
                placeholder = { Text("Search by name or code...") },
                modifier = Modifier.width(320.dp)
            )
        }

        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(buyers) { b ->
                Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Row(modifier = Modifier.padding(16.dp).fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Column {
                            Text(b.name, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                            Text("Code: ${b.buyer_code} | Contact: ${b.contact_person ?: "N/A"} (${b.phone ?: ""})", fontSize = 12.sp, color = Color.Gray)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Active Orders: ${b.active_orders_count}", fontWeight = FontWeight.Medium)
                            Text("Total Ordered: %,.0f pairs".format(b.total_ordered_pairs), fontSize = 12.sp, color = Color.Gray)
                            Text("Outstanding: %,.0f pairs".format(b.outstanding_production_pairs), fontSize = 12.sp, color = Color(0xFFF59E0B))
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun OrdersScreen(apiClient: ErpApiClient) {
    var orders by remember { mutableStateOf<List<OrderSummaryDto>>(emptyList()) }
    var selectedOrderId by remember { mutableStateOf<Int?>(null) }
    var orderDetail by remember { mutableStateOf<OrderDetailDto?>(null) }
    var showReviseDialog by remember { mutableStateOf(false) }
    var newDeliveryDate by remember { mutableStateOf("") }
    var reviseReason by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    fun loadOrders() {
        scope.launch {
            orders = apiClient.getOrders().getOrDefault(emptyList())
        }
    }

    LaunchedEffect(Unit) { loadOrders() }

    LaunchedEffect(selectedOrderId) {
        selectedOrderId?.let { id ->
            scope.launch {
                orderDetail = apiClient.getOrderDetail(id).getOrNull()
            }
        }
    }

    Column(modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("Order Planning & Tracking", fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Button(onClick = { loadOrders() }) { Text("Refresh") }
        }

        Row(modifier = Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            // Orders List
            Card(modifier = Modifier.weight(0.45f).fillMaxHeight(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                LazyColumn(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(orders) { o ->
                        val isSelected = o.id == selectedOrderId
                        Surface(
                            modifier = Modifier.fillMaxWidth().clickable { selectedOrderId = o.id },
                            color = if (isSelected) MaterialTheme.colorScheme.primary.copy(alpha = 0.25f) else Color.Transparent,
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                    Text(o.order_code, fontWeight = FontWeight.Bold)
                                    Text(o.status, fontSize = 12.sp, color = MaterialTheme.colorScheme.primary)
                                }
                                Text("Buyer: ${o.buyer_name ?: "N/A"}", fontSize = 12.sp, color = Color.Gray)
                                Text("Model: ${o.style_model} (%,.0f pairs)".format(o.total_quantity), fontSize = 12.sp)
                                Text("Delivery: ${o.current_delivery_date} (${o.remaining_working_days} workdays left)", fontSize = 11.sp, color = Color(0xFFF59E0B))
                            }
                        }
                    }
                }
            }

            // Order Details View
            Card(modifier = Modifier.weight(0.55f).fillMaxHeight(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                orderDetail?.let { det ->
                    Column(modifier = Modifier.padding(16.dp).fillMaxSize(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Column {
                                Text(det.order_code, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                                Text("${det.buyer_name} - ${det.style_model}", color = Color.Gray, fontSize = 13.sp)
                            }
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(onClick = {
                                    newDeliveryDate = det.current_delivery_date
                                    showReviseDialog = true
                                }) { Text("Revise Date") }

                                OutlinedButton(onClick = {
                                    Desktop.getDesktop().browse(URI(apiClient.getOrderXlsxUrl(det.id)))
                                }) { Text("Export XLSX") }
                            }
                        }

                        // Summary badges
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            MetricCard("Total Qty", "%,.0f".format(det.total_quantity), "Pairs", Modifier.weight(1f))
                            MetricCard("Completed", "%,.0f".format(det.completed_pairs), "${det.completion_percentage}%", Modifier.weight(1f))
                            MetricCard("Remaining", "%,.0f".format(det.outstanding_pairs), "Pairs", Modifier.weight(1f))
                            MetricCard("Workdays", "${det.remaining_working_days}", "Until Delivery", Modifier.weight(1f))
                        }

                        Text("Section-wise Operations & Progress", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.weight(1f)) {
                            items(det.routes) { r ->
                                Card(
                                    modifier = Modifier.fillMaxWidth(),
                                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.background)
                                ) {
                                    Column(modifier = Modifier.padding(12.dp)) {
                                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                            Text("${r.section_name} (${r.status})", fontWeight = FontWeight.Bold)
                                            Text(if (r.is_completed) "COMPLETED" else "IN PROGRESS", color = if (r.is_completed) Color(0xFF10B981) else Color(0xFFF59E0B), fontSize = 12.sp)
                                        }
                                        r.operations.forEach { op ->
                                            Row(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                                                Text(" • ${op.operation_name}: %,.0f / %,.0f ${op.unit}".format(op.completed_quantity, op.required_quantity), fontSize = 12.sp)
                                                Text("Daily Target: %,.0f".format(op.daily_target), fontSize = 12.sp, color = MaterialTheme.colorScheme.primary)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                } ?: Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("Select an order to view planning details")
                }
            }
        }
    }

    if (showReviseDialog && orderDetail != null) {
        AlertDialog(
            onDismissRequest = { showReviseDialog = false },
            title = { Text("Revise Delivery Date") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Current Delivery Date: ${orderDetail?.current_delivery_date}")
                    OutlinedTextField(
                        value = newDeliveryDate,
                        onValueChange = { newDeliveryDate = it },
                        label = { Text("New Delivery Date (YYYY-MM-DD)") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = reviseReason,
                        onValueChange = { reviseReason = it },
                        label = { Text("Reason for Deadline Revision") },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            },
            confirmButton = {
                Button(onClick = {
                    scope.launch {
                        apiClient.reviseDeliveryDate(orderDetail!!.id, newDeliveryDate, reviseReason)
                        showReviseDialog = false
                        loadOrders()
                        orderDetail = apiClient.getOrderDetail(orderDetail!!.id).getOrNull()
                    }
                }) { Text("Save Revision") }
            },
            dismissButton = {
                TextButton(onClick = { showReviseDialog = false }) { Text("Cancel") }
            }
        )
    }
}

@Composable
fun ProductionEntryScreen(apiClient: ErpApiClient) {
    var orders by remember { mutableStateOf<List<OrderSummaryDto>>(emptyList()) }
    var selectedOrder by remember { mutableStateOf<OrderDetailDto?>(null) }
    var selectedRouteId by remember { mutableStateOf<Int?>(null) }
    var selectedOpId by remember { mutableStateOf<Int?>(null) }

    var entryDate by remember { mutableStateOf("2026-10-07") }
    var quantity by remember { mutableStateOf("") }
    var acceptedQty by remember { mutableStateOf("") }
    var rejectedQty by remember { mutableStateOf("0") }
    var remarks by remember { mutableStateOf("") }
    var isOverride by remember { mutableStateOf(false) }

    var statusMessage by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        orders = apiClient.getOrders().getOrDefault(emptyList())
    }

    Column(modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text("Manual Daily Production Entry", fontSize = 24.sp, fontWeight = FontWeight.Bold)

        Card(modifier = Modifier.width(600.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(modifier = Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                OutlinedTextField(
                    value = entryDate,
                    onValueChange = { entryDate = it },
                    label = { Text("Production Date (YYYY-MM-DD)") },
                    modifier = Modifier.fillMaxWidth()
                )

                // Select Order
                Text("Select Order:", fontWeight = FontWeight.Bold)
                LazyColumn(modifier = Modifier.height(120.dp)) {
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
                            color = if (selectedOrder?.id == o.id) MaterialTheme.colorScheme.primary.copy(alpha = 0.2f) else Color.Transparent
                        ) {
                            Text("${o.order_code} - ${o.customer_ref} (${o.style_model})", modifier = Modifier.padding(6.dp), fontSize = 13.sp)
                        }
                    }
                }

                selectedOrder?.let { det ->
                    Text("Selected Operation:", fontWeight = FontWeight.Bold)
                    det.routes.forEach { r ->
                        r.operations.forEach { op ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                RadioButton(
                                    selected = selectedOpId == op.id,
                                    onClick = {
                                        selectedRouteId = r.id
                                        selectedOpId = op.id
                                    }
                                )
                                Text("${r.section_name} -> ${op.operation_name} (Balance: %,.0f ${op.unit})".format(op.balance_quantity), fontSize = 13.sp)
                            }
                        }
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        OutlinedTextField(
                            value = quantity,
                            onValueChange = {
                                quantity = it
                                acceptedQty = it
                            },
                            label = { Text("Total Qty") },
                            modifier = Modifier.weight(1f)
                        )
                        OutlinedTextField(
                            value = acceptedQty,
                            onValueChange = { acceptedQty = it },
                            label = { Text("Accepted Qty") },
                            modifier = Modifier.weight(1f)
                        )
                        OutlinedTextField(
                            value = rejectedQty,
                            onValueChange = { rejectedQty = it },
                            label = { Text("Rejected Qty") },
                            modifier = Modifier.weight(1f)
                        )
                    }

                    OutlinedTextField(
                        value = remarks,
                        onValueChange = { remarks = it },
                        label = { Text("Remarks (e.g. Shift / Machine info)") },
                        modifier = Modifier.fillMaxWidth()
                    )

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = isOverride, onCheckedChange = { isOverride = it })
                        Text("Authorized Overproduction Override", fontSize = 12.sp)
                    }

                    Button(
                        onClick = {
                            scope.launch {
                                val res = apiClient.recordProductionEntry(
                                    orderId = det.id,
                                    routeId = selectedRouteId ?: det.routes.first().id,
                                    operationId = selectedOpId ?: det.routes.first().operations.first().id,
                                    entryDate = entryDate,
                                    quantity = quantity.toDoubleOrNull() ?: 0.0,
                                    acceptedQty = acceptedQty.toDoubleOrNull() ?: 0.0,
                                    rejectedQty = rejectedQty.toDoubleOrNull() ?: 0.0,
                                    remarks = remarks,
                                    isOverride = isOverride
                                )
                                if (res.isSuccess) {
                                    statusMessage = "Production entry recorded successfully!"
                                    quantity = ""
                                    acceptedQty = ""
                                    // Refresh order detail
                                    selectedOrder = apiClient.getOrderDetail(det.id).getOrNull()
                                } else {
                                    statusMessage = "Error: " + (res.exceptionOrNull()?.message ?: "Failed")
                                }
                            }
                        },
                        modifier = Modifier.fillMaxWidth().height(48.dp)
                    ) {
                        Text("Submit Daily Production")
                    }

                    statusMessage?.let {
                        Text(it, color = if (it.startsWith("Error")) MaterialTheme.colorScheme.error else Color(0xFF10B981))
                    }
                }
            }
        }
    }
}

@Composable
fun ReportsScreen(apiClient: ErpApiClient) {
    var orders by remember { mutableStateOf<List<OrderSummaryDto>>(emptyList()) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        orders = apiClient.getOrders().getOrDefault(emptyList())
    }

    Column(modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text("Excel XLSX and CSV Production Reports", fontSize = 24.sp, fontWeight = FontWeight.Bold)
        Text("Downloads authoritative planning workbooks directly generated with OpenPyXL and Python CSV engine.", color = Color.Gray)

        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(orders) { o ->
                Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Row(
                        modifier = Modifier.padding(16.dp).fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text("${o.order_code} - ${o.customer_ref}", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                            Text("Buyer: ${o.buyer_name} | Qty: %,.0f pairs | Delivery: ${o.current_delivery_date}".format(o.total_quantity), fontSize = 12.sp, color = Color.Gray)
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Button(onClick = {
                                Desktop.getDesktop().browse(URI(apiClient.getOrderXlsxUrl(o.id)))
                            }) {
                                Text("Download 7-Sheet XLSX")
                            }
                            OutlinedButton(onClick = {
                                Desktop.getDesktop().browse(URI(apiClient.getOrderCsvUrl(o.id)))
                            }) {
                                Text("Download CSV")
                            }
                        }
                    }
                }
            }
        }
    }
}
